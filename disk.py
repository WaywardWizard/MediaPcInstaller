from collections import defaultdict as dd
import re
import tempfile
import json
import pathlib
from util import bash,getDictionaryFromKeyValueString,userConfirm

class Disk:
    '''Concerned with initializing a disk
    
    initializing: Partitioning and formatting partitions with a filesystem.
    '''
    SYSTEM_MOUNTS = '/proc/mounts'
    ALIGNMENT_OFFSET=1  #In Mb. Align partition to physical block

    #--getsz returns in units of sector. This is the size of a sector in bytes
    # See $> man blcokdev, /--getsz
    BLKDEV_GETSZ_SECTORSZ=512 

    class Partition:
        
        PARTED_PARTTYPE_EXT4='8300'
        PARTED_PARTTYPE_BIOSBOOT='ef02'
 
        MKFS_FSTYPE=['ext4'] #mkfs for all these partitions

        def _data(self):
            _data=dd(lambda:'')

            for k,v in self.__dict__.items():
                if not callable(v):
                    dd[k]=v
            return(_data)

        def __del__(self):
            '''Unmounts and deletes any temporary mountpoint that exists for ptn'''
            if self.tempmount is not None:
                bash(f'sudo umount {self.tempmount}')
                bash(f'rmdir {self.tempmount}')


        def __init__(self,disk,specifier):
            '''Build partition from dictionary or a device path '''

            # Partition info
            self.partitionnbr=None
            self.partitiontype=None      #This is the parted's internal code
            self.startsector=None
            self.endsector=None
            self.partitionsectors=None

            # Block info
            self.partitionlabel=None
            self.partitionuuid=None

            self.fsblocksize=None
            self.fslabel=None
            self.fsuuid=None
            self.fstype=None

            self.device=None
            self.mountpoint=None
            self.mountoptions=None
            self.tempmount=None

            self.disk=disk
            self.inpartitiontable=False
            
            
            self.doonmkfs=[]

            if isinstance(specifier,str):
                self.device=specifier
                self._initFromDevicePath()
            else:
                self._initFromDictionary()

        def _initFromDevicePath(self):

            mountsline=bash(f'cat {Disk.SYSTEM_MOUNTS} | grep {self.device}',False).stdout
            try:
                if mountsline.returncode == 0:
                    mountinfo=mountsline.split()
                    self.mountpoint=mountinfo[2]
                    self.fstype=mountinfo[3]
                    self.mountoptions=mountinfo[4]
            except OSError: 
                print('Device {} not mounted'.format(self.device))

            blkid=getDictionaryFromKeyValueString(bash('sudo blkid -o export {}' % self.device).stdout)

            self.partitionlabel=blkid['PARTLABEL']
            self.partitionuuid=blkid['PARTUUID']

            self.fslabel=blkid['LABEL']
            self.fsuuid=blkid['UUID']
            self.fstype=blkid['TYPE']
            self.fsblocksize=blkid['BLOCK_SIZE']
            self._setPartitionInfo()
            self.inpartitiontable=True
        
        def _setPartitionInfo(self):
            ''' Get partition info identified by start and end sector, or device path'''
            if self.device is not None:
                partitioninfo=map(
                        lambda x:x.rstrip(';'),
                        filter(
                            lambda x:re.match('[0-9]',x) is not None,
                            bash('sudo parted -m {} unit s print' % self.device)
                                .stdout
                                .splitlines()
                            )
                        ).pop().split(':')


            elif self.startsector is not None and self.endsector is not None:
                partitioninfo=filter(
                    lambda x:re.match('.*{}s:{}s'.format(self.startsector,self.endsector), x),
                    map(
                        lambda x:x.rstrip(';'),
                        filter(
                            lambda x:re.match('[0-9]',x) is not None,
                            bash('sudo parted -m {} unit s print' % self.device).stdout.splitlines()
                            )
                        )
                    ).pop().split(':') # Only one entry in the array, this pttn

            else:
                # Partition needs start and end sector defined or else it must exist already
                raise ValueError('Not correctly initialized')
 
            self.partitionnumber=partitioninfo[0]
            self.startsector=partitioninfo[1].rtrim('s')
            self.endsector=partitioninfo[2].rtrim('s')
            self.partitionsectors=partitioninfo[3].rtrim('s')
            self.partitiontype=partitioninfo[4]
            self.partitionlabel=partitioninfo[5]
            self.partitionflags=partitioninfo[6]

        def getMountpoint(self):
            '''Mounts partition if not mounted and returns the mountpoint
            '''
            if self.mountpoint is not None:
                return(pathlib.Path(self.mountpoint))
            else:
                self.tempmount=tempfile.mkdtemp()
                self.mountpoint=self.tempmount
                bash(f'sudo mount {self.device} {self.mountpoint}')


        def writeToPartitionTable(self):
            '''Adds this partition to partition table'''

            # CHECK THAT kwarg device is not overwritten
            bash('sudo parted {device} mkpart {partitionlabel} {fstype} {startsector}s {endsector}s'.format(device=self.disk.device,**self.data()))

            if self.partitiontype==Disk.Partition.PARTED_PARTTYPE_BIOSBOOT:
                bash('sudo parted {device} set {partition} bios_grub on'
                        .format(device=self.device,**self.data()))
    
            self._setPartitionInfo()
            self.inpartitiontable=True

        def mkfs(self):
            if self.fstype in Disk.Partition.MKFS_FSTYPE:
                bash(f'sudo mkfs -t {self.fstype} {self.device}')
                
            for f in self.doonmkfs:
                f()
            
                
            
        def onmkfs(self, fn):
            self.doonmkfs.append(fn)

        def _initFromDictionary(self,d):
            ''' Create a partition with parameters as per given dictionary 
            The partition may not actually exist - until the partition table is written
            
            '''
            for k in self.data():
                if d.haskey(k):
                    setattr(self,k,d[k])

    def __init__(self, path):
        
        self.diskdata=json.loads(bash(f'sudo sfdisk -l -J {path}').stdout)

        self.alignmentoffset=Disk.ALIGNMENT_OFFSET
    
        self.confirmedAsExpectedDisk=False
        self.ptchanged=False

        self.pttype=self.diskdata['partitiontable']['label']
        self.firstsector=self.diskdata['partitiontable']['firstlba']
        self.lastsector=self.diskdata['partitiontable']['lastlba']
        sectorcount=self.lastsector-self.firstsector - 1

        self.bytessector=self.diskdata['partitiontable']['sectorsize']# nbr of bytes per physical sector

        self.device=path
        self._partitions=[Disk.Partition(self,x) for x in self._listDevices()]

        blkid=getDictionaryFromKeyValueString(bash('sudo blkid -o export {}'.path).stdout)
        self.ptuuid=blkid['PTUUID']
        self.pttype=blkid['PTTYPE']
        self.space=int(bash('sudo blkdev --getsz {}' % path).stdout)*Disk.BLKDEV_GETSZ_SECTORSZ

        blkdev_bytessector=int(bash('sudo blkdev --getss {}' % path).stdout)
        if(blkdev_bytessector!=self.bytessector):
            raise ValueError(f'blkdev --getsz {self.device} and fdisk -l {self.device} disagree.'+
                             f'blkdev {blkdev_bytessector}\nsfdisk {self.bytessector}')
                
        self.sectorcount=self.space%self.bytesPerSector
        if(self.sectorcount != sectorcount):
            raise ValueError(f'blkdev ({self.sectorcount}) and sfdisk ({sectorcount}) disagree on sectorcount')
        
    def _listDevices(self):
        '''List all block devices for this disk''' 
        devices=bash(f'sudo sfdisk -qlo device {self.device}').stdout.splitlines()
        devices=[x for x in devices if re.match(r'/',x)] # remove heading
        return(devices)

    def _getNextFreeSector(self):
        endsectors=[x.endsector for x in self._partitions]
        if len(endsectors)==0:
            return(self.alignmentoffset*pow(2,20))
        return(max([x.endsector]))
        
        
    def addPartition(self, size, partitionlabel, fslabel):
        ''' Add a partition of given size in MB to partition table'''
        bytesize=size*pow(2,20)
        startsector=self._getNextFreeSector()
        _data={
            'startsector':startsector,
            'endsector':startsector+bytesize,
            'partitiontype':Disk.Partition.PARTED_PARTTYPE_BIOSBOOT, # linux partition type for gdisk
            'fstype':'ext4',
            'partitionlabel':partitionlabel,
            'fslabel':fslabel,
            }
        self._partitions.append(Disk.Parition(_data))
        self.ptchanged=True

    def _data(self):
        _data=dd(lambda:'')

        for k,v in self.__dict__.items():
            if not callable(v):
                dd[k]=v

        return(_data)


    def writePartitionTable(self):
        ''' Write partition table consistent with partitions of disk. 
        Return True if table written, else False
        '''
        if not self.confirmedAsExpectedDisk:
            self.confirmExpectedDisk()
        if not self.ptchanged:
            return(False)
        
        bash('sudo parted {device} mklabel {pttype}' % self.data())
        for p in self._partitions:
            p.writeToPartitionTable()
       
        print('Partition table written. Checking alignment')
        for p in self._partitions:
            print(bash('sudo parted {} align-check optimal {}' % (self.device,p.partitionnbr)).stdout)

        print('Partition table is now;')
        print(bash(f'sudo parted {self.device} print').stdout)

        self.ptchanged=False
        
    def mkfsOnPartitions(self):
        for p in self._partitions:
            p.mkfs()

    def getPartitionByFsLabel(self,label):
        for p in self._partitions:
            if p.fslabel==label or p.partitionlabel==label:
                return(p)
        return(None)

    def confirmExpectedDisk(self):
        print('Is this disk the right disk?')
        print(bash('sudo sfdisk -l disk').stdout)
        userConfirm('Is this the right disk? Y|N')
        print('Disk has the following partitions, confirm each one')
        for p in self._partitions:
            print('{}:{}:{}'.format(p.device,p.fstype,p.mountpoint))
            print('For this disk, is this an expected partition? Y|N')
        print('Disk now cleared to be have its partition table rewritten.')
        self.confirmedAsExpectedDisk=True

class GrubDisk(Disk):
    '''Disk, which will have grub2 installed for bootloading
    '''
    GRUB_BOOT_SIZE=1
    GRUB_DATA_SIZE=32
   
    GRUB_BOOT_PARTLABEL='grub_bios_boot'
    GRUB_DATA_PARTLABEL='grub_data'
    GRUB_DATA_FSLABEL='grub_data'
    
    def __init__(self, path):
        '''Initialize disk so that partitions may be edited. 
        
        Attempts to make grub data partition in the next available area on disk. 
        Assumes there is a 1Mibi block of free space at beginning of disk
        '''

        super().__init__(path)
        
        self.bootpartition=None
        self.grubpartition=None
        self.grubmenu=[]

        self._initGrubBiosBoot()
        self._initGrubDataPartition()
        
    
    def _installGrub(self):
        '''Installs grub to the grub data partition once its fs has been intialized
        
        This is invoked once a filesystem for this partition exists.
        '''
        # Mount data partition
        
        grubdatamount=tempfile.mkdtemp()
        bash('sudo mount {} {}'.format(self.grubpartition.device,grubdatamount))
        self.grubpartition.mountpoint=grubdatamount
        self.grubpartition.tempmount=grubdatamount

        # Install grub, specifying path to grub data partition
        # NB: Grub will make this path relative to the filesystems root,
        # see function grub_make_system_path_relative_to_its_root_os of grub source 
        option='--boot-directory={}'.format(self.grubdatadir)

        print("Installing grub to disk {}'s mbr, boot partition {} & grub data parttiion {}"
                .format(self.device,self.bootpartition.device,self.grubpartition.device))

        result = bash('sudo grub-install {} {}'.format(option, self.device))

        print(result.stdout)
        
    def mkGrubMenuEntry(self, 
                        name:str,
                        partition:Disk.Partition,
                        kernelpath:str,
                        kernelarg:str):

        entry='''
            menuentry {} {{
                search --set=root --label {}
                linux {} {}
            }}
        '''.format(name,partition.fslabel,kernelpath,kernelarg)
        
        self.grubmenu.append(entry)
        
    def updateGrubMenu(self):
        '''Updates the grub menu in grub_data'''
        if self.grubdatadir is None:
            raise ValueError('Both partition table needs to be written and fs inited todo this.')
        else:
            bash('sudo grub-mkconfig -o {}'.format(self.grubdatadir))

    def _initGrubDataPartition(self,size=GRUB_DATA_SIZE):
        ''' Install grub_data partition, format it.
        
        The installation of grub with $> grub install /dev/thisdisk will put all required
        files here later
        '''
        
        startsector=self._getNextFreeSector()
        endsector=startsector+ ( (size*pow(2,20)) % self.bytessector ) - 1

        grub_data={
            'startsector':startsector,
            'endsector':endsector,
            'partitionlabel':GrubDisk.GRUB_DATA_PARTLABEL,
            'partitiontype':Disk.Partition.PARTED_PARTTYPE_BIOSBOOT,
            'fstype':'ext4',
            'fslabel':GrubDisk.GRUB_DATA_FSLABEL,
        }

        self.grubpartition=Disk.Partition(grub_data)
        self._partitions.append(self.grubpartition)
        self.grubpartition.onmkfs(self._installGrub)
        self.ptchanged=True

            
    def _initGrubBiosBootPartition(self,size=GRUB_BOOT_SIZE):
        ''' Install grub_bios_boot partition
        
        This partition reserves space for the grub core.img to prevent a fs or os 
        modifying it. ,
        
        Grub installs to 1 sector on disk, a list of addresses to load, which are
        used to load grubs core.img. core.img will load device drivers that enable
        access to the partition holding grub files. (grub_data)
        
        ASSUMES: 
            *) The sector returned by self._getNextFreeSector() has enough space 
            following it for this partition.
            *) The sector returned by self._getNextFreeSector() is within the first
            2[Gibi] - size[Mibi] of disk space
        '''
        boot_startsector=self._getNextFreeSector()

        bytesize=size*pow(2,20)
        nsector=bytesize%self.bytessector

        boot_endsector=boot_startsector+nsector-1
        
        grub_boot={
            'partitiontype':Disk.Partition.PARTED_PARTTYPE_BIOSBOOT, #gdisk bios boot type
            'startsector':boot_startsector,
            'endsector':boot_endsector,
            'partitionlabel':GrubDisk.GRUB_BOOT_PARTLABEL,
        }
        
        self.bootpartition=Disk.Partition(grub_boot)
        self._partitions.append(self.bootpartition)
        self.ptchanged=True
        