from disk import Disk,Partition
from util import bash,dlFile
from pathlib import Path
import config
import stat
import os
from config import ROOT

EMPTY_GRUB_CUSTOM_MENU='''
#!/bin/sh
exec tail -n +3 $0
'''

GRUB_PATH=Path(ROOT,'grub/')
GRUB_THEME_PATH=f'{GRUB_PATH}/theme'
GRUB_THEME_SOURCE_PATH=f'{GRUB_PATH}/themeSource'
GRUB_THEMES={
    'Zenburn':{
        'url':'https://github.com/trefmanic/grub2-zenburn'
        },
    'Primitive':{
        'url':'https://gitlab.com/fffred/primitivistical-grub.git'
        },
    'PolyDark':{
        'url':'https://github.com/shvchk/poly-dark'
        },
    'Griffin':{
        'url':'https://github.com/LordShenron/Grub-Themes/tree/griffin-grub-remix'
    }
}
GRUB_MKCONFIG_OPTS={
    'GRUB_SAVEDEFAULT=true',
    'GRUB_TIMEOUT=-1',
    'GRUB_TIMEOUT_STYLE=menu',
}
GRUB_SYSTEM_CONFIG_DIR='/etc/grub.d'
GRUB_MENU_FILE='50_custom'
GRUB_MENU_WHITELIST=['00_header']


def getThemes():
    """Get configured themes"""
    for theme,data in GRUB_THEMES.items():
        dlFile(data['url'],Path(config.ROOT,GRUB_THEME_SOURCE_PATH),True)
        print(theme)

            
        
class GrubDisk(Disk):
    """ Disk, which will have grub2 installed for bootloading
    """
    GRUB_BOOT_SIZE=1
    GRUB_DATA_SIZE=32
   
    GRUB_BOOT_PARTLABEL='grub_bios_boot'
    GRUB_DATA_PARTLABEL='grub_data'

    GRUB_DATA_FSLABEL='grub_data'
    
    GRUB_PARTFLAG='bios_grub'
    
    # None for boot partition
    
    def __init__(self, path):
        '''Initialize disk so that partitions may be edited. 
        
        Attempts to make grub data partition in the next available area on disk. 
        Assumes there is a 1Mibi block of free space at beginning of disk
        '''

        super().__init__(path)
        
        self.rawGrubmenu=EMPTY_GRUB_CUSTOM_MENU
        self.grubmenu=[]

        self._initGrubBiosBootPartition()
        self._initGrubDataPartition()
        

        
    def _installGrub(self):
        '''Installs grub to the grub data partition once its fs has been intialized
        
        This is invoked once a filesystem for this partition exists.
        '''
                

        # Install grub, specifying path to grub data partition
        # NB: Grub will make this path relative to the filesystems root,
        # see function grub_make_system_path_relative_to_its_root_os of grub source 
        option=f'--boot-directory={self.grubpartition.getMountpoint()}'
        print(f"Installing grub to disk {self.device}'s mbr, boot partition {self.grubbootpartition} & grub data partition {self.grubpartition}")
        result = bash(f'sudo grub-install {option} {self.device}')
        print(result.stdout)
        
    def addGrubMenuEntry(self, 
                        name:str,
                        partition:Partition,
                        kernelpath:str,
                        kernelarg:str,
                        cl=None):

        entry=f'''
            menuentry {name} 
            {f"--class={cl}" if cl is not None else ""} {{
                search --set=root --label {partition.fslabel}
                linux {kernelpath} {kernelarg}

            }}
        '''
        self.grubmenu.append(entry)
        
    def updateGrubMenu(self):
        '''Updates the grub menu in grub_data'''
        
        # Write menu file. Disable all others. 
        resetExecuteFile=[]
        for entry in os.scandir(Path(GRUB_SYSTEM_CONFIG_DIR)):
            if entry.is_file() and not entry.name in GRUB_MENU_WHITELIST:
                entryStat=entry.stat()
                if stat.filemode(entryStat.st_mode)[-1]=='x':
                    resetExecuteFile.append(entry.path)
                    bash(f'sudo chmod -x {entry.path}')

        menuFilePath=Path(ROOT,GRUB_MENU_FILE)
        menuFile=open(menuFilePath,'wt')
        menuFile.write(EMPTY_GRUB_CUSTOM_MENU)
        [menuFile.write(entry) for entry in self.grubmenu ]
        menuFile.close()
        bash(f'sudo chmod +x {menuFilePath}')
        bash(f'sudo cp {menuFilePath} {GRUB_SYSTEM_CONFIG_DIR}')
        bash(f'sudo grub-mkconfig -o {self.grubpartition.mountpoint}')
        os.unlink(menuFilePath)
        [bash(f'sudo chmod +x {p}') for p in resetExecuteFile]
        # Renable others. Remove menu file.

    def _initGrubDataPartition(self,size=GRUB_DATA_SIZE):
        ''' Install grub_data partition, format it.
        
        The installation of grub with $> grub install /dev/thisdisk will put all required
        files here later
        '''


        uuid=self.partitiontable.addPartition(size, 
                                         fstype='ext4',
                                         partitionlabel=GrubDisk.GRUB_DATA_PARTLABEL);
        

        self.grubpartition=self.partitiontable.getPartitionBy(uuid)
        self._installGrub()

    def _initGrubBiosBootPartition(self,size=GRUB_BOOT_SIZE):
        ''' Install grub_bios_boot partition
        
        This partition reserves space for the grub core.img to prevent a fs or os 
        modifying it. ,
        
        Grub installs to 1 sector on disk, a list of addresses to load, which are
        used to load grubs core.img. core.img will load device drivers that enable
        access to the partition holding grub files. (grub_data)
        
        ASSUMES: 
            *) The sector returned by self._getNextFreeSectorBlock() has enough space 
            following it for this partition.
            *) The sector returned by self._getNextFreeSectorBlock() is within the first
            2[GiB] - size[MiB] of disk space
        '''
        uuid=self.partitiontable.addPartition(size, 
                                         partitionlabel=GrubDisk.GRUB_BOOT_PARTLABEL,
                                         partitionflag=[GrubDisk.GRUB_PARTFLAG]);
        self.grubbootpartition=self.partitiontable.getPartitionBy(uuid)
