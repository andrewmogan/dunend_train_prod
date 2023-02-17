import yaml, os, pathlib, shutil
import numpy as np
from yaml import Loader
import larndsim
from datetime import timedelta
from project_base import project_base


REQUIRED = dict(GEOMETRY=os.path.join(pathlib.Path(__file__).parent.resolve(),'geometry'),
    MPVMPR=os.path.join(pathlib.Path(__file__).parent.resolve(),'config'),
    PIXEL_LAYOUT='larndsim/pixel_layouts/',
    DET_PROPERTIES='larndsim/detector_properties/',
    RESPONSE='larndsim/bin',
    )

class project_larndsim(project_base):

    def parse_project_config(self,cfg):

        cfg['G4_MACRO_PATH']=os.path.join(cfg['JOB_SOURCE_DIR'],'g4.mac')

        # Check required configuration files
        for word in REQUIRED.keys():
            opt1 = 'USE_' + word
            opt2 = 'SEARCH_' + word
            
            if opt1 in cfg and opt2 in cfg:
                print(f'ERROR: both "USE" and "SEARCH" requested for {word} (only one is allowed).')
                print(f'{opt1}: {cfg[opt1]}')
                print(f'{opt2}: {cfg[opt2]}')
                raise ValueError('Please fix the configuration file.')
                
            if not opt1 in cfg and not opt2 in cfg:
                print(f'ERROR: keyword not found (need either USE_{word} or SEARCH_{word})')
                print(f'{cfg}')
                raise ValueError('Please fix the configuration file.')

            # option 1: take the path specified by the user
            if opt1 in cfg:
                if not os.path.isfile(opt1):
                    print(f'ERROR: {word} file not found at the specified location.')
                    raise FileNotFoundError(f'{cfg[opt1]}')
                cfg[word]=cfg[opt1]

            # option 2: grab from larnd-sim repository
            if opt2 in cfg:
                if not 'LARNDSIM_REPOSITORY' in cfg:
                    print(f'ERROR: to SEARCH {word}, you must provide LARNDSIM_REPOSITORY in the config.')
                    raise ValueError('Please add local larnd-sim installation path to LARNDSIM_REPOSITORY in the config')

                path = os.path.join(REQUIRED[word],cfg[opt2])
                if not path.startswith('/'):
                    path = os.path.join(cfg['LARNDSIM_REPOSITORY'],path)

                if not os.path.isfile(path):
                    print(f'Searched a file {cfg[opt2]} but not found...')
                    raise FileNotFoundError(f'{path}')

                cfg[word]=path

    def gen_project_script(self,cfg):

        macro = self.gen_g4macro(os.path.basename(cfg['MPVMPR']))
        with open(cfg['G4_MACRO_PATH'],'w') as f:
            f.write(macro)
            f.close()
        self.gen_job_script(cfg)

        for key in REQUIRED.keys():
            self.COPY_FILES.append(cfg[key])


    def gen_g4macro(self, mpv_config):
        macro=f'''
/edep/hitSeparation TPCActive_shape -1 mm
/edep/hitSagitta drift 1.0 mm
/edep/hitLength drift 1.0 mm
/edep/db/set/neutronThreshold 0 MeV
/edep/db/set/lengthThreshold 0 mm
/edep/db/set/gammaThreshold 0 MeV
/edep/random/timeRandomSeed
/edep/update

/generator/kinematics/bomb/config {mpv_config}
/generator/kinematics/bomb/verbose 0
/generator/kinematics/set bomb 

/generator/count/fixed/number 1
/generator/count/set fixed
/generator/add

        '''
        return macro


    def gen_job_script(self, cfg):

        cmd_edepsim = f'''edep-sim \
-g {os.path.basename(cfg['GEOMETRY'])} \
-e {int(cfg['NUM_EVENTS'])} \
-o {cfg['JOB_OUTPUT_ID']}-edepsim.root \
{os.path.basename(cfg['G4_MACRO_PATH'])}
    '''

        cmd_dumptree = f'''dumpTree.py \
    {cfg['JOB_OUTPUT_ID']}-edepsim.root {cfg['JOB_OUTPUT_ID']}-edepsim.h5
    '''

        cmd_larndsim = f'''{cfg['LARNDSIM_SCRIPT']} \
--pixel_layout={os.path.basename(cfg['PIXEL_LAYOUT'])} \
--detector_properties={os.path.basename(cfg['DET_PROPERTIES'])} \
--response_file={os.path.basename(cfg['RESPONSE'])} \
--event_separator=eventID \
--save_memory='resource.h5' \
--input_filename={cfg['JOB_OUTPUT_ID']}-edepsim.h5 \
--output_filename={cfg['JOB_OUTPUT_ID']}-larndsim.h5
    '''

        self.PROJECT_SCRIPT=f'''#!/bin/bash
date
echo "starting a job"

export PATH=$HOME/.local/bin:$PATH

nvidia-smi &> jobinfo_gpu.txt

OUTPUT_NAME={cfg['JOB_OUTPUT_ID']}

date
echo "Running edep-sim"
echo {cmd_edepsim}
{cmd_edepsim} &>> log_edepsim.txt

date
echo "Running dumpTree"
echo {cmd_dumptree}
{cmd_dumptree} &>> log_dumptree.txt

date
echo "Running larnd-sim"
echo {cmd_larndsim}
{cmd_larndsim} &>> log_larndsim.txt

date
echo "Removing the response file..."
rm {os.path.basename(cfg['RESPONSE'])}
echo "Exiting"
    
    '''

if __name__ == '__main__':
    import sys
    if not len(sys.argv) == 2:
        print(f'Invalid number of the arguments ({len(sys.argv)})')
        print(f'Usage: {os.path.basename(__file__)} $JOB_CONFIGURATION_YAML')
        sys.exit(1)

    if not sys.argv[1].endswith('.yaml'):
        print('The argument must be a yaml file with .yaml extension.')
        print(f'(provided: {os.path.basename(sys.argv[1])})')
        sys.exit(2)

    p=project_larndsim()
    p.generate(sys.argv[1])
    sys.exit(0)
