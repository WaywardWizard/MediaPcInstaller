from grub.grub import GrubDisk
from config import config
import json
from pathlib import Path
from util import bash,dlFile
import tempfile
import shutil
import os

dev=Path('/dev/sdb')

disk = GrubDisk(dev)

for osid,data in config['os'].items():
    for ptn,info in data['partition'].items():
        uuid=disk.partitiontable.addPartition(info['size'], info['partitionlabel'],fslabel=info['fslabel'],fstype=info['fstype'])
        info['uuid']=uuid
        

def getFirstPartitionOffset(imageFile):
    data=json.loads(bash('sfdisk -l {} -J'.format(imageFile)).stdout)
    sectorsize=data['partitiontable']['sectorsize']
    firstsector=min([n['start'] for n in data['partitiontable']['partitions']])
    return(sectorsize*firstsector)

def cleanup(workingDirectory, mounts):
    for m in mounts:
        bash(f'sudo umount {m}')
    shutil.rmtree(workingDirectory)

try:

    workingDirectory=Path(tempfile.mkdtemp())
    mounts=[]

    oldcwd=os.getcwd()
    os.chdir(workingDirectory)

    for osid in config['os'].keys():

        osdata=config['os'][osid]
        ostarball=Path(osdata['tarballpath'])

        zipImageFile=ostarball.parts[-1]
        imageFile=ostarball.stem

        # Install openelec, grub menu entry
        if not ostarball.exists():
            print(f'Retrieving {osid} image')
            dlFile(osdata['tarballurl'],ostarball)
            
        shutil.copy(ostarball,workingDirectory)

        print(f'Extracting {osid} image')
        bash(f'gunzip {zipImageFile}')

        print(f'Mounting {osid} image')
        offset=getFirstPartitionOffset(imageFile)
        mountpoint=Path(workingDirectory,imageFile+'.mnt')
        mounts.append(mountpoint)
        bash(f'mkdir {mountpoint}')
        bash(f'sudo mount -o loop,offset={offset} {imageFile} {mountpoint}')
        
        systemPartition=disk.partitiontable.getPartitionBy(osdata['partition']['system']['partitionlabel'],'partlabel')
        print(f'Transferring files in mounted {osid} image to {systemPartition}')

        # Viashell for explansion of glob
        bash(f'sudo cp -r {mountpoint}/* {systemPartition.getMountpoint()}',viashell=True)
        
        # Add bootmenu entry
        for menuItem in osdata['bootloader']:
            for menuName,menuData in menuItem.items():
                disk.addGrubMenuEntry(
                    menuName,
                    systemPartition,
                    menuData['kpath'],
                    menuData['karg'],
                    menuData['class']
                    )

        
except Exception as e:
    cleanup(workingDirectory,mounts )
    raise e

finally:
    cleanup(workingDirectory,mounts )
    
# REgenerate boot menu
disk.updateGrubMenu()


