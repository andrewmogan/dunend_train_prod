import yaml, os, pathlib, shutil
from yaml import Loader
import larndsim

REQUIRED = dict(GEOMETRY=os.path.join(pathlib.Path(__file__).parent.resolve(),'geometry'),
    MPVMPR=os.path.join(pathlib.Path(__file__).parent.resolve(),'config'),
    PIXEL_LAYOUT='larndsim/pixel_layouts/',
    DET_PROPERTIES='larndsim/detector_properties/',
    RESPONSE='larndsim/bin',
    )

def parse(data):
    cfg = yaml.safe_load(data)
    res = dict(cfg)
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
            res[word]=cfg[opt1]

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

            res[word]=path

    # Check the storage directory and create this job's output directory
    if not 'STORAGE_DIR' in cfg:
        raise KeyError('STORAGE_DIR key is missing in the configuration file.')
    if not os.path.isdir(cfg['STORAGE_DIR']):
        raise FileNotFoundError(f'Storage path {cfg["STORAGE_DIR"]} is invalid.')

    sdir=os.path.abspath(os.path.join(cfg['STORAGE_DIR'],f'output_{os.getpid()}'))
    if os.path.isdir(sdir):
        raise OSError(f'Storage directory already have a sub-dir {sdir}')
    res['STORAGE_DIR']=sdir

    # define a job source directory
    res['JOB_SOURCE_DIR'] = os.path.join(sdir,'job_source')

    return res

def gen_g4macro(mpv_config):
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

def gen_submission_script(cfg):
    job_work_dir = 'dtnp_${SLURM_JOB_ID}_${SLURM_ARRAY_TASK_ID}'
    output_id = 'output_${SLURM_JOB_ID}_${SLURM_ARRAY_TASK_ID}'
    script=f'''
#!/bin/bash
#SBATCH --job-name=dntp-{os.getpid()}
#SBATCH --nodes=1
#SBATCH --partition={cfg['SLURM_PARTITION']}
#SBATCH --output=job-%A-%a.out
#SBATCH --error=job-%A-%a.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cfg['SLURM_CPU']}
#SBATCH --mem-per-cpu={round(cfg['SLURM_MEM']/cfg['SLURM_CPU'])}
#SBATCH --time={cfg['SLURM_TIME']}                                                                                                
#SBATCH --gpus={cfg['SLURM_GPU']}:1
#SBATCH --array=1-{cfg['SLURM_NUM_JOBS']}

mkdir -p {cfg['SLURM_WORK_DIR']} 
cd {cfg['SLURM_WORK_DIR']}

scp -r {cfg['JOB_SOURCE_DIR']} {job_work_dir}
cd {job_work_dir}

date
echo "starting a job"

printenv &> env.txt

OUTPUT_NAME={output_id}

date
echo "Running edep-sim"
edep-sim -g {cfg['GEOMETRY']} -e {int(cfg['NUM_EVENTS'])} -o $OUTPUT_NAME-edepsim.root {cfg['G4_MACRO_PATH']} &> p0_edepsim.log

date
echo "Running dumpTree"
dumpTree.py $OUTPUT_NAME-edepsim.root $OUTPUT_NAME-edepsim.h5 &>> p1_dump.log

date
echo "Running larnd-sim"
{cfg['LARNDSIM_SCRIPT']} --pixel_layout={cfg['PIXEL_LAYOUT']} \
--detector_properties={cfg['DET_PROPERTIES']} --response_file={cfg['RESPONSE']} --event_separator=eventID \
--input_filename=$OUTPUT_NAME-edepsim.h5 --output_filename=$OUTPUT_NAME-larndsim.h5 &>> p2_lrandsim.log

date
echo "Copying the output (removing response file as it's too large)"
rm {cfg['RESPONSE']}
scp -r {job_work_dir} {cfg['STORAGE_DIR']}

date
echo "Exiting"
    
    '''
    return script

def main(cfg):
    
    if cfg.endswith('.yaml'):
        with open(cfg,'r') as f:
            cfg = f.read()

    # parse the configuration            
    cfg = parse(cfg)
    cfg_data = yaml.dump(cfg,default_flow_style=False)

    jsdir = cfg['JOB_SOURCE_DIR']
    sdir  = cfg['STORAGE_DIR']

    try:
        # Create the job source and the storage directories
        os.mkdir(jsdir)
        os.mkdir(sdir)

        # Log the config contents
        with open(os.path.join(jsdir,'source.yaml'),'w') as f:
            f.write(cfg_data)
            f.close()

        # Copy geometry, detector properties, response, pixel layout data files
        for key in REQUIRED.keys():
            src,target=cfg[key],os.path.basename(cfg[key])
            shutil.copyfile(src,os.path.join(jsdir,target))
            cfg[key]=target
            
        # Generate G4 macro
        cfg['G4_MACRO_PATH']=os.path.join(jsdir,'g4.mac')
        with open(cfg['G4_MACRO_PATH'],'w') as f:
            f.write(gen_g4macro(os.path.basename(cfg['MPVMPR'])))
            f.close()


        # Generate a run script
        with open(os.path.join(jsdir,'run.sh'),'w') as f:
            f.write(gen_submission_script(cfg))
            f.close()

    except (KeyError, OSError, IsADirectoryError):
        if os.path.isdir(jsdir):
            shutil.rmtree(jsdir)
        if os.path.isdir(sdir):
            os.remove(sdir)

    print(f'Created job source scripts at {jsdir}')
    print(f'Job output will be sent to {sdir}')

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
    main(sys.argv[1])
    sys.exit(0)