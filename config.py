openelecimage='OpenELEC-Generic.x86_64-8.0.4.img'
lakkaimage='Lakka-Generic.x86_64-2.3.2.img'
repopath='/home/ben/eclipse-workspace/MediaPcInstaller/'
config = {
    'os': {
        'openelec':{
            'tarballurl':'http://releases.openelec.tv/{}.gz'.format(openelecimage),
            'tarballpath':'{}{}.gz'.format(repopath,openelecimage),
            'bootloader':{
                'kernelArgument':'ssh quiet'
                },
            'partition':{
                'system':{
                    'size':1*1024,
                    'fslabel':'oe_system_root',
                    'partitionlabel':'oe_root'
                    },
                'data':{
                    'size':12*1024,
                    'fslabel':'oe_data',
                    'partitionlabel':'oe_data'
                    },
                },
            },
        'lakka':{
            'tarballurl':'http://le.builds.lakka.tv/Generic.x86_64/{}.gz'.format(lakkaimage),
            'tarballpath':'{}{}.gz'.format(repopath,lakkaimage),
            'bootloader':{
                'entries':[
                    ]
                },
            'partition':{
                'system':{
                    'size':1*1024,
                    'fslabel':'lakka_system_root',
                    'partitionlabel':'lakka_root',
                    },
                'data':{
                    'size':36*1024,
                    'fslabel':'lakka_data',
                    'partitionlabel':'lakka_data',
                    },
                },
            }
        },
    }   