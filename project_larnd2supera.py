import glob, os
import numpy as np
import larnd2supera

class project_larndsim(project_base):

    def parse_project_config(self,cfg):

        if not 'SUPERA_CONFIG' in cfg:
            raise KeyError(f'SUPERA_CONFIG key is missing in the configuration data!\n{cfg}')

        # make sure config is valid
        valid_configs = larnd2supera.config.list_config()
        if not cfg['SUPERA_CONFIG'] in valid_configs:
            if not os.path.isfile(cfg['SUPERA_CONFIG']):
                raise FileNotFoundError(f'SUPERA_CONFIG {cfg["SUPERA_CONFIG"]} not found.')
            self.COPY_FILES.append(cfg['SUPERA_CONFIG'])
            cfg['SUPERA_CONFIG'] = os.path.basename(cfg['SUPERA_CONFIG'])

        filelist = glob.glob(cfg['GLOB'])
        if len(filelist) < 1:
            raise KeyError(f'GLOB {cfg["GLOB"]} returned no file!')

        # assert the file count matches the requested job count
        if not len(filelist) == int(cfg['SLURM_NUM_JOBS']):
            print(f'GLOB {cfg["GLOB"]} returned {len(filelist)} files')
            print(f'But requested job count is {cfg["SLURM_NUM_JOBS"]} (must match)')
            raise ValueError(f'GLOB {cfg["GLOB"]} returned unexpected file count')

        # create a filelist
        with open(os.path.join(cfg['JOB_SOURCE_DIR'],'flist.txt'),'w') as f:
            for name in filelist:
                f.write(name)
                self.BIND_PATHS.append(self.get_top_dir(name))

        script = '''
import sys
jobid = int(sys.argv[1])
print(open('flist.txt','r').split()[jobid])
        '''
        with open(os.path.join(cfg['JOB_SOURCE_DIR'],'input_name.py'),'w') as f:
            f.write(script)



    def gen_project_script(self,cfg):

        cmd_supera = f'''run_larnd2supera.py \
-o {cfg['JOB_OUTPUT_ID']}-larcv.root \
-c {cfg['SUPERA_CONFIG']}
        '''

        script = f'''#!/bin/bash

echo "Starting a job"
date

echo "Copying a file"
SOURCE_FILE_NAME=`python3 input_name.py $SLURM_ARRAY_TASK_ID`
INPUT_FILE_NAME=`basename $SOURCE_FILE_NAME`
echo scp $SOURCE_FILE_NAME $INPUT_FILE_NAME
scp $SOURCE_FILE_NAME $INPUT_FILE_NAME
date

echo "Running Supera"
{cmd_supera} $INPUT_FILE_NAME
date

echo "Removing the input"
rm $INPUT_FILE_NAME
date

echo "Touching the input filename"
touch $INPUT_FILE_NAME
date

echo "Exiting"
        '''