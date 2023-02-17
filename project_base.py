import yaml, os, pathlib, shutil
import numpy as np
from yaml import Loader
from datetime import timedelta

class project_base():

    def __init__(self):
        self.COPY_FILES=[]
        self.PROJECT_SCRIPT=''
        self.BIND_PATHS=[]

    def get_top_dir(self,path):
        p=pathlib.Path(path)
        return p.parents[len(p.parents)-2]

    def parse_project_config(self,cfg):
        '''
        Function to be implemented.
        cfg is a configuration dictionary.
        Parse configuration as necessary.
        '''
        pass

    def gen_project_script(self,cfg):
        '''
        Function to be implemented.
        cfg is a configuration dictionary.
        Fill the contents of a project script in self.PROJECT_SCRIPT attribute.
        Fill the list of files to be copied to self.COPY_FILES.
        Those files will be available under the job directory with the same name.
        '''
        pass

    def parse(self,data):
        cfg = yaml.safe_load(data)
        # SLURM_TIME converted to seconds automatically
        # convert back to HH:MM:SS format
        cfg['SLURM_TIME'] = str(timedelta(seconds=cfg['SLURM_TIME']))
        res = dict(cfg)

        # Check the storage directory and create this job's output directory
        if not 'STORAGE_DIR' in cfg:
            raise KeyError('STORAGE_DIR key is missing in the configuration file.')
        if not os.path.isdir(os.path.expandvars(cfg['STORAGE_DIR'])):
            raise FileNotFoundError(f'Storage path {cfg["STORAGE_DIR"]} is invalid.')

        sdir=os.path.abspath(os.path.join(os.path.expandvars(cfg['STORAGE_DIR']),f'production_{os.getpid()}'))
        if os.path.isdir(sdir):
            raise OSError(f'Storage directory already have a sub-dir {sdir}')
        res['STORAGE_DIR']=sdir

        # define a job source directory
        res['JOB_SOURCE_DIR'] = os.path.join(sdir,'job_source')

        # add job work directory and output name
        res['JOB_WORK_DIR'  ] = 'job_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}'
        res['JOB_OUTPUT_ID' ] = 'output_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}'
        res['JOB_LOG_DIR'   ] = os.path.join(res['STORAGE_DIR'],'slurm_logs')

        # ensure singularity image is valid
        if not 'SINGULARITY_IMAGE' in cfg:
            raise KeyError('SINGULARITY_IMAGE must be specified in the config.')
        if not os.path.isfile(os.path.expandvars(cfg['SINGULARITY_IMAGE'])):
            raise FileNotFoundError(f'Singularity image invalid in the config:{cfg["SINGULARITY_IMAGE"]}')
        # resolve symbolic link
        res['SINGULARITY_IMAGE']=os.path.abspath(os.path.realpath(os.path.expandvars(cfg['SINGULARITY_IMAGE'])))

        # define a copied image name
        if cfg.get('STORE_IMAGE',True):
            res['JOB_IMAGE_NAME']=os.path.join(sdir,f'image_{os.getpid()}.sif')
            res['STORE_IMAGE']=True
        else:
            res['JOB_IMAGE_NAME']=res['SINGULARITY_IMAGE']

        # define paths to be bound to the singularity session
        self.BIND_PATHS.append(self.get_top_dir(res['STORAGE_DIR']))
        self.BIND_PATHS.append(self.get_top_dir(res['SLURM_WORK_DIR']))
        self.BIND_PATHS.append(self.get_top_dir(res['JOB_IMAGE_NAME']))
        self.BIND_PATHS.append(self.get_top_dir(res['JOB_SOURCE_DIR']))

        return res


    def gen_submission_script(self,cfg):

        # singularity bind flag
        bflag = None
        for pt in np.unique(self.BIND_PATHS):
            if bflag is None:
                bflag=f'-B {str(pt)}'
            else:
                bflag += f',{str(pt)}'

        script=f'''#!/bin/bash
#SBATCH --job-name=dntp-{os.getpid()}
#SBATCH --nodes=1
#SBATCH --partition={cfg['SLURM_PARTITION']}
#SBATCH --output={cfg['JOB_LOG_DIR']}/slurm-%A-%a.out
#SBATCH --error={cfg['JOB_LOG_DIR']}/slurm-%A-%a.out
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cfg['SLURM_CPU']}
#SBATCH --mem-per-cpu={round(cfg['SLURM_MEM']/cfg['SLURM_CPU'])}G
#SBATCH --time={cfg['SLURM_TIME']}                                                                                                
#SBATCH --array=1-{cfg['SLURM_NUM_JOBS']}
'''
        if 'SLURM_GPU' in cfg:
            script += f'#SBATCH --gpus={cfg["SLURM_GPU"]}:1\n'
        if 'SLURM_EXCLUDE' in cfg:
            script += f'#SBATCH --exclude="{cfg["SLURM_EXCLUDE"]}"\n'
        if 'SLURM_NODELIST' in cfg:
            script += f'#SBATCH --nodelist="{cfg["SLURM_EXCLUDE"]}"\n'

        script += f'''
mkdir -p {cfg['SLURM_WORK_DIR']} 
cd {cfg['SLURM_WORK_DIR']}

JOB_WORK_DIR=$(printf "job_%d_%04d" $SLURM_ARRAY_JOB_ID $SLURM_ARRAY_TASK_ID)

scp -r {cfg['JOB_SOURCE_DIR']} $JOB_WORK_DIR

cd $JOB_WORK_DIR

export PATH=$HOME/.local/bin:$PATH

printenv &> jobinfo_env.txt
uname -a &> jobinfo_node.txt

chmod 774 run.sh

singularity exec --nv {bflag} {cfg['JOB_IMAGE_NAME']} ./run.sh

date
echo "Copying the output"

cd ..
scp -r $JOB_WORK_DIR {cfg['STORAGE_DIR']}/
    
    '''
        return script


    def generate(self,cfg):
        
        if cfg.endswith('.yaml'):
            with open(cfg,'r') as f:
                cfg = f.read()

        # parse the configuration            
        cfg = self.parse(cfg)
        cfg_data = yaml.dump(cfg,default_flow_style=False)

        jsdir = cfg['JOB_SOURCE_DIR']
        sdir  = cfg['STORAGE_DIR']
        ldir  = cfg['JOB_LOG_DIR']

        try:
            # Create the job source and the storage directories
            print(f'Creating a dir: {sdir}')
            os.makedirs(sdir)
            print(f'Creating a dir: {jsdir}')
            os.makedirs(jsdir)
            print(f'Creating a dir: {ldir}')
            os.makedirs(ldir)
            print(f'Using a singularity image: {cfg["SINGULARITY_IMAGE"]}')
            if cfg['STORE_IMAGE']:
                print('Copying the singularity image file.')
                print(f'Destination: {cfg["JOB_IMAGE_NAME"]}')
                shutil.copyfile(cfg['SINGULARITY_IMAGE'],cfg['JOB_IMAGE_NAME'])

            # Generate a submission script
            with open(os.path.join(jsdir,'submit.sh'),'w') as f:
                f.write(self.gen_submission_script(cfg))
                f.close()

            #
            # Perform project-specific tasks
            #
            # Parse configuration for the project
            self.parse_project_config(cfg)
            # Generate a project script contents
            self.gen_project_script(cfg)
            # Generate a job script
            with open(os.path.join(jsdir,'run.sh'),'w') as f:
                f.write(self.PROJECT_SCRIPT)
                f.close()
            # Copy necessary files
            for f in self.COPY_FILES:
                src,target=f,os.path.basename(f)
                shutil.copyfile(src,os.path.join(jsdir,target))

            #
            # Log the config contents
            #
            with open(os.path.join(jsdir,'source.yaml'),'w') as f:
                f.write(cfg_data)
                f.close()


        except (KeyError, ValueError, OSError, IsADirectoryError) as e:
            if os.path.isdir(jsdir):
                shutil.rmtree(jsdir)
            if cfg['STORE_IMAGE'] and os.path.isfile(cfg['JOB_IMAGE_NAME']):
                os.remove(cfg['JOB_IMAGE_NAME'])
            if os.path.isdir(sdir):
                shutil.rmtree(sdir)
            if os.path.isdir(ldir):
                os.rmdir(ldir)
            print('Encountered an error. Aborting...')
            raise e

        print(f'Created job source scripts at {jsdir}')
        print(f'Job output will be sent to {sdir}')
        print(f'\nTo submit a job, type:\n\nsbatch {os.path.join(jsdir,"submit.sh")}\n')
        return True


class project_example(project_base):


    def parse_project_config(self,cfg):

        return

    def gen_project_script(self,cfg):

        return '#!/bin/bash\necho "hello world"\n'

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

    p=project_example()
    p.generate(sys.argv[1])
    sys.exit(0)
