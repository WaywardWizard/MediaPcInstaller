from pathlib import Path
openelecimage='OpenELEC-Generic.x86_64-8.0.4.img'
lakkaimage='Lakka-Generic.x86_64-2.3.2.img'
repopath='/home/ben/eclipse-workspace/MediaPcInstaller/'
config = {
    'os': {
        'openelec':{
            'tarballurl':'http://releases.openelec.tv/{}.gz'.format(openelecimage),
            'tarballpath':'{}{}.gz'.format(repopath,openelecimage),
            'bootloader':[
                {'OpenELEC':{
                    'karg':'ssh quiet',
                    'kpath':'/KERNEL',
                    'class':'kodi'
                    }},
                ],
            'partition':{
                'system':{
                    'size':1*1024,
                    'fslabel':'oe_system_root',
                    'partitionlabel':'oe_root',
                    'fstype':'ext4',
                    },
                'data':{
                    'size':12*1024,
                    'fslabel':'oe_data',
                    'partitionlabel':'oe_data',
                    'fstype':'ext4',
                    },
                },
            },
        'lakka':{
            'tarballurl':'http://le.builds.lakka.tv/Generic.x86_64/{}.gz'.format(lakkaimage),
            'tarballpath':'{}{}.gz'.format(repopath,lakkaimage),
            'bootloader':[
                {'Lakka':{
                    'karg':'ssh quiet',
                    'kpath':'/KERNEL',
                    'class':'lakka'
                    }
                },
                ],
            'partition':{
                'system':{
                    'size':1*1024,
                    'fslabel':'lakka_system_root',
                    'partitionlabel':'lakka_root',
                    'fstype':'ext4',
                    },
                'data':{
                    'size':36*1024,
                    'fslabel':'lakka_data',
                    'partitionlabel':'lakka_data',
                    'fstype':'ext4',
                    },
                },
            }
        },
    }   

ROOT=Path(__file__).parent
