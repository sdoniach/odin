
import os
import subprocess
from nose import SkipTest

from mdtraj import trajectory

from odin import xray
from odin.testing import skip, ref_file


try:
    import matplotlib
    MPL = True
except:
    MPL = False

try:
    from odin import gpuscatter
    GPU = True
except ImportError as e:
    GPU = False


try:
    import openmm
    OPENMM = True
except ImportError as e:
    OPENMM = False
    
# see if we are on Travis CI -- which for whatever reason does not play well with 
# these tests that use subprocess. todo : find out why and see if we can fix it
try:
    if os.environ['TRAVIS'] == 'true':
        TRAVIS = True
    else:
        TRAVIS = False
except:
    TRAVIS = False
    

class TestShoot(object):
    
    def setup(self):
        self.file = ref_file('ala2.pdb')
        
    def test_single_gpu(self):
        if not GPU: raise SkipTest
        if TRAVIS: raise SkipTest
        cmd = 'odin.xray.shoot -s %s -n 1 -m 512 -o testshot.shot > /dev/null 2>&1' % self.file
        subprocess.check_call(cmd, shell=True)
        if not os.path.exists('testshot.shot'):
            raise RuntimeError('no output produced')
        else:
            s = xray.Shotset.load('testshot.shot')
            os.remove('testshot.shot')
            
    def test_cpu(self):
        if TRAVIS: raise SkipTest
        cmd = 'odin.xray.shoot -s %s -n 1 -m 1 -o testshot2.shot > /dev/null 2>&1' % self.file
        subprocess.check_call(cmd, shell=True)
        if not os.path.exists('testshot2.shot'):
            raise RuntimeError('no output produced')
        else:
            s = xray.Shotset.load('testshot2.shot')
            os.remove('testshot2.shot')
        
@skip
def test_plotiq():
    if not MPL: raise SkipTest
    if TRAVIS: raise SkipTest
    cmd = 'odin.xray.plotiq -i %s -m 1.0 > /dev/null 2>&1' % ref_file('reference_shot.shot')
    subprocess.check_call(cmd, shell=True)
    if not os.path.exists('intensity_plot.pdf'):
        raise RuntimeError('no output produced')
    else:
        os.remove('intensity_plot.pdf')
