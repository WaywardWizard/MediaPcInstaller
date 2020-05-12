from collections import defaultdict as dd
import re
import ast
import tempfile
from pathlib import Path
from util import bash,getDictionaryFromKeyValueString,userConfirm

"""
@TODO:
Get fstype to reflect in partition data (no fs, no relection)
Make fs before attempting to mount
"""


class PartitionTable:
    def __init__(self, disk):
        self.disk=disk

        self.partitiondata={}
        self._data={}
        self._updatePartitionTableData()
        
        self.uuid=self._data['blkid']['PTUUID']
        self.type=self._data['blkid']['PTTYPE']

        
    def __str__(self):
        s=f"{self.type} partition table on {self.disk.device}\n"
        for p in self._partitions:
            s+=str(p)
        return(s)

    def _updatePartitionTableData(self):
        """Use sfdisk, parted and blkid to read partition table information from disk"""
        if self.disk is None:
            raise ValueError("Disk must be set to read partition table")

        self._data['sfdisk']=\
            ast.literal_eval(bash(f'sudo sfdisk -l -J {self.disk.device}').stdout)
        self._data['parted']=\
            list(map(
                lambda x:x.rstrip(';').split(':'),
                    filter(
                        lambda x:re.match('[0-9]',x) is not None,
                        bash(f'sudo parted -m {self.disk.device} unit s print')
                            .stdout
                            .splitlines()
                        )
                    ))
        self._data['blkid']=getDictionaryFromKeyValueString(\
            bash(f'sudo blkid -o export {self.disk.device}').stdout)

        self.firstlba=self._data['sfdisk']['partitiontable']['firstlba']
        self.lastlba=self._data['sfdisk']['partitiontable']['lastlba']
        self.bytessector=self._data['sfdisk']['partitiontable']['sectorsize']

        def _collatePartitionData(sfdiskData):

            device = Path(sfdiskData['node'])
            blkidData=getDictionaryFromKeyValueString(\
                bash(f'sudo blkid -o export {device}').stdout)

            start = int(sfdiskData['start'])

            partedData = list(filter(lambda x: int(x[1].rstrip('s'))==start, self._data['parted'])).pop()
            data={
                'device':device,
                'startsector':start,
                'endsector':int(partedData[2].rstrip('s')),
                'sectorcount':int(sfdiskData['size']),
                'fstype':partedData[4],
                'fslabel':blkidData['LABEL'],
                'fsuuid':blkidData['UUID'],
                'partlabel':sfdiskData['name'],
                'partuuid':sfdiskData['uuid'],
                'partflag':partedData[6],
                'partnbr':int(partedData[0])
            }
            self.partitiondata[device]=data                 #By device
            self.partitiondata[sfdiskData['name']]=data
            self.partitiondata[sfdiskData['uuid']]=data     #By uuid
            self.partitiondata[blkidData['UUID']]=data     #By fsuuid
            
        if 'partitions' in self._data['sfdisk']['partitiontable']:
            [_collatePartitionData(d) for d in self._data['sfdisk']['partitiontable']['partitions']]

        self._updatePartitions()

    def _updatePartitions(self):
        """Update partition objects to match what is in the table currently"""
        self._partitions=set([Partition(self,Path(x)) for x in self._listDevices()])

    def _listDevices(self):
        if not 'partitions' in self._data['sfdisk']['partitiontable']:
            return([])
        return([n['node'] for n in self._data['sfdisk']['partitiontable']['partitions']])

    def _getNextFreeSectorBlock(self, after=None):
        """Returns the next free contiguous set of usable adresses [start,end]
        
        :param after: Find chunk starting on this sector or after
        :return:(None,None) if not found, else (start, end)
        """

        if(after is None):after=self.firstlba
        after=self.disk.alignStartSector(after)

        end=set()
        [end.add(x.endsector) for x in self._partitions]
        
        # Ending at beginning of disk for initial partition
        # Only want aligned start sectors orthis algo wont work
        end.add(self.disk.alignStartSector(self.firstlba)-1)

        orderedEnd=list(end)
        orderedEnd.sort()
        
        start=set()
        [start.add(x.startsector) for x in self._partitions]
        orderedStart=list(start)
        orderedStart.sort()
        
        def _findNextStart(onOrAfter):
            if(len(start)==0):
                return(self.lastlba)

            for s in orderedStart:
                if s>=onOrAfter:
                    return(s)
                
            return(self.lastlba)

        for e in orderedEnd:
            if not e+1 in start and (e+1) >= after:
                if e+1<self.lastlba:
                    return((e+1, _findNextStart(e+1)-1))
                
        return((None,None))
 
    def _findSpace(self,size, after=None):
        """Find space for a partition of size
        
        :param after: Find space starting after or on this sector
        :param before: Find space on or before this sector
        :param size: size in MiB
        """
        if after is None:
            after=self.firstlba

        bytesize=size*pow(2,20)
        startsector,maxendsector=self._getNextFreeSectorBlock(after)

        if startsector is None:
            raise ValueError(f"Cant find space for a partition fo {size}MiB on {self.disk}")

        lengthInSectors=bytesize//self.bytessector + bool(bytesize%self.bytessector)

        # Align sectors to physical block
        startsector=self.disk.alignStartSector(startsector)
        endsector=startsector+lengthInSectors-1

        if endsector > maxendsector:
            return(self._findSpace(size,after=maxendsector))

        return(startsector, endsector)

    def getPartitionBy(self,idvalue,identifier='partuuid'):
        for p in self._partitions:
            if getattr(p,identifier)==idvalue:
                return p
        return(None)

    def rmPartition(self,partition:'Partition'):
        bash(f'sudo parted {self.disk.device} rm {partition.partnbr}')
        self._updatePartitionTableData()

    def addPartition(self, size, partitionlabel, keep=False,fslabel=None,fstype='', partitionflag=[]):
        """Add a partition of given size in MiB to partition table
        
        Where a partition for the given label exists, and is the same size, its uuid
        will be returned when its filesystem is the same as fstype or if fstype is blank.
        Where the partition size differs, the partition with the given partition label
        will be deleted and recreated at the appropriate size.

        :param: keep - when True, if the partition with given label exists keep it
        :return: uuid of existing or created partition
        """
        if not self.disk.confirmedAsExpectedDisk:
            self.disk.confirmExpectedDisk()
        
        existingPartition=self.getPartitionBy(partitionlabel, 'partlabel')
        if not existingPartition is None:
            if existingPartition.mibsize == size and keep:
                if fstype=='' or fstype==existingPartition.fstype:
                    return(existingPartition.partuuid)
            # Replacing 
            self.rmPartition(existingPartition)
            existingPartition=None
            
        currentDevices=set(self._listDevices())
        startsector,endsector=self._findSpace(size)
        bash(f'sudo parted {self.disk.device} mkpart {partitionlabel} {fstype} {startsector}s {endsector}s')
       
        self._updatePartitionTableData()
        newDevice=set(self._listDevices())-currentDevices
        print(f'Making partition {partitionlabel} on {self.disk.device}')
        if(len(newDevice))==0:
            raise OSError(f'Partition {partitionlabel} could not be created on {self.disk.device}')

        newDevice=Path(newDevice.pop())

        newPartition=self.getPartitionBy(newDevice,'device')

        for flag in partitionflag:
            bash(f'sudo parted {self.disk.device} set {newPartition.partnbr} {flag} on')

        print('Partition table written. Checking alignment')
        print(bash(f'sudo parted {self.disk.device} align-check optimal {newPartition.partnbr}').stdout)
        
        newPartition.mkfs(fstype, fslabel)
        return(newPartition.partuuid)

class Partition:
    
    PARTED_PARTTYPE_EXT4='8300'
    PARTED_PARTTYPE_BIOSBOOT='ef02'

    MKFS_FSTYPE=['ext4'] #mkfs for all these partitions
    DEFAULT_FSTYPE='ext4'
    
    class Mountpoint:

        SYSTEM_MOUNTS = '/proc/mounts'

        def __init__(self, partition):
            """
            :sideeffect: Creates tempdir and mounts parititon there if not 
                already mounted. This will be cleaned up on object.__del__()
            """

            #Check false for if grep finds nothing
            mountsline=bash(f'cat {Partition.Mountpoint.SYSTEM_MOUNTS} | grep {partition.device}',check=False)

            if mountsline.returncode == 0:
                mountinfo=mountsline.stdout.split()
                self.mountpoint=Path(mountinfo[1])
                self.mountoptions=mountinfo[3]
            else:
                self.tempmount=Path(tempfile.mkdtemp())
                self.mountpoint=self.tempmount
                bash(f'sudo mount {partition.device} {self.mountpoint}')
                
        def __str__(self):
            return(str(self.mountpoint))

        def __del__(self):
            '''Unmounts and deletes any temporary mountpoint that exists for ptn'''
            if hasattr(self,'mountpoint'):
                bash(f'sudo umount {self.mountpoint}')
                bash(f'rmdir {self.mountpoint}')
        
    def __str__(self):
        return(f'{self.mountpoint} {self.partlabel} {self.fstype} {self.mountpoint} {self.mibsize}[MiB]')

    def __init__(self, table:PartitionTable, idvalue:str):
        """Build partition from dictionary or a device path 

        :param table: On which partition is located
        :param uuid|devicepath: Identifies partition this object represents
        :seealso: PartitionTable::_updatePartitionTableData._collatePartitionData
        """
        self.table=table
        self.doonmkfs=[]
        self.mountpoint = None
        for k,v in self.table.partitiondata[idvalue].items():
            setattr(self,k,v)
        self.bytesize=self.sectorcount*self.table.bytessector
        self.mibsize= self.bytesize / pow(2,20)

    def mkfs(self,typevalue,label):
        """Format partition filesystem and run pending callbacks
        :note: Only fs types in Disk.Partition.MKFS_FSTYPE will be
            prepared
        """
        if typevalue in Partition.MKFS_FSTYPE:
            self.fslabel=label
            print(f'Building {typevalue} filesystem on {self.device}')
            bash(f'sudo mkfs -t {typevalue} -L {self.fslabel} {self.device}')
            for f in self.doonmkfs:
                f()
        
    def onmkfs(self, fn):
        """Adds a callback to be run once the filesystem has been prepared
        """
        self.doonmkfs.append(fn)

    def getMountpoint(self):
        if not self.mountpoint is None:
            return(self.mountpoint)

        self.mountpoint=Partition.Mountpoint(self)
        return(self.getMountpoint())


class Disk:
    '''Concerned with initializing a disk
    
    initializing: Partitioning and formatting partitions with a filesystem.
    '''
    ALIGNMENT_OFFSET=1  #In Mb. Align partition to physical block
    BOOT_FLAG='boot'

    def __str__(self):
        return(f'{self.device} {self.GiBcount}[GiB]')

    def __init__(self, devicepath):
        
        self.device=devicepath
        self.partitiontable=PartitionTable(self)
        self.alignmentoffset=Disk.ALIGNMENT_OFFSET
        self.confirmedAsExpectedDisk=False
        self.bytecount=int(bash(f'sudo blockdev --getsize64 {self.device}').stdout)
        self.GiBcount=int(self.bytecount/(pow(2,30)))
        self.bytessector=int(bash(f'sudo blockdev --getpbsz {self.device}').stdout)
        self.sectorcount=self.bytecount/self.bytessector
       
    def _data(self):
        _data=dd(lambda:'')
        for k,v in self.__dict__.items():
            if not callable(v):
                dd[k]=v
        return(_data)

    def alignStartSector(self,start):
        """Given a sector to start with, make sure it is aligned on an alignment boundary
        :return: Start adjusted upward to alignment boundary if not on one
        """
        sectorsPerBoundary = pow(2,20)/self.bytessector
        if (start % sectorsPerBoundary)==0:
            return(start)
        
        wholeSectorsToStart=start//sectorsPerBoundary
        return((wholeSectorsToStart+1)*sectorsPerBoundary)

    def confirmExpectedDisk(self): 
        print('Is this disk the right disk?')
        print(bash(f'sudo sfdisk -l {self.device}').stdout)
        userConfirm('Is this the right disk? Y|N')

        print('Disk has the following partitions, confirm each one')
        print(bash(f'sudo parted -l {self.device}').stdout)
        #userConfirm('Are these the right partitions? Y|N')
        print('Disk now cleared to be have its partition table modified.')
        self.confirmedAsExpectedDisk=True
