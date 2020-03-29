from disk import GrubDisk
from config import config
import json
from pathlib import Path
from util import bash,dlFile
import tempfile
import shutil

dev=Path('/dev/sdb')

disk = GrubDisk(dev)

for os,data in config['os'].items():
    for ptn,info in data['partition']:
        disk.addPartition(info['size'], info['partitionlabel'],info['fslabel'])
        
disk.writePartitionTable()
disk.mkfsOnPartitions()

workingDirectory=Path(tempfile.mkdtemp())

def getFirstPartitionOffset(file):
    data=json.loads(bash('sfdisk -l {} -J'.format(file)).stdout)
    sectorsize=data['partitiontable']['sectorsize']
    firstsector=min([n['start'] for n in data['partitiontable']['partitions']])
    return(sectorsize*firstsector)

for os in config['os'].keys:
    osdata=config['os'][os]
    ostarball=Path(osdata['tarballpath'])

    # Install openelec, grub menu entry
    if not ostarball.exists():
        dlFile(osdata['tarballurl'],ostarball)
        
    shutil.copy(ostarball,workingDirectory)
    cwd=os.getcwd()
    os.chdir(workingDirectory)
    print('CWD is: {}'.format(bash('pwd').stdout))
    bash('gunzip -c {} > image'.format(ostarball))
    offset=getFirstPartitionOffset(Path('image'))
    bash('mkdir mnt')
    bash('sudo mount -o loop,offset={} ./image ./mnt'.format(offset))
    systemPartition=disk.getPartitionByFsLabel(osdata['partition']['system']['fslabel'])
    shutil.copytree('./mnt',systemPartition.getMountpoint())
    os.chdir(cwd)
    
# REgenerate boot menu


