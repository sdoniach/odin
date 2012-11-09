#!/usr/bin/env python


import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

from numpy.linalg import norm

def form_factor(qvector, atomz):
    
    mq = np.sum( np.power(qvector, 2) )
    qo = mq / (16.*np.pi*np.pi)
    
    if ( atomz == 1 ):
        fi = 0.493002*np.exp(-10.5109*qo)
        fi+= 0.322912*np.exp(-26.1257*qo)
        fi+= 0.140191*np.exp(-3.14236*qo)
        fi+= 0.040810*np.exp(-57.7997*qo)
        fi+= 0.003038
    
    elif ( atomz == 8):
        fi = 3.04850*np.exp(-13.2771*qo)
        fi+= 2.28680*np.exp(-5.70110*qo)
        fi+= 1.54630*np.exp(-0.323900*qo)
        fi+= 0.867000*np.exp(-32.9089*qo)
        fi+= 0.2508

    elif ( atomz == 26):
        fi = 11.7695*np.exp(-4.7611*qo)
        fi+= 7.35730*np.exp(-0.307200*qo)
        fi+= 3.52220*np.exp(-15.3535*qo)
        fi+= 2.30450*np.exp(-76.8805*qo)
        fi+= 1.03690

    elif ( atomz == 79):
        fi = 16.8819*np.exp(-0.4611*qo)
        fi+= 18.5913*np.exp(-8.6216*qo)
        fi+= 25.5582*np.exp(-1.4826*qo)
        fi+= 5.86*np.exp(-36.3956*qo)
        fi+= 12.0658
        
    # else approximate with Nitrogen
    else:
        fi = 12.2126*np.exp(-0.005700*qo)
        fi+= 3.13220*np.exp(-9.89330*qo)
        fi+= 2.01250*np.exp(-28.9975*qo)
        fi+= 1.16630*np.exp(-0.582600*qo)
        fi+= -11.529
        
    return fi
    
    
def rquaternion(rfloat=None):
    
    if rfloat == None:
        rfloat = np.random.rand(3)
    
    q = np.zeros(4)
    
    s = rfloat[0]
    sig1 = np.sqrt(s)
    sig2 = np.sqrt(1.0 - s)
    
    theta1 = 2.0 * np.pi * rfloat[1]
    theta2 = 2.0 * np.pi * rfloat[2]
    
    w = np.cos(theta2) * sig2
    x = np.sin(theta1) * sig1
    y = np.cos(theta1) * sig1
    z = np.sin(theta2) * sig2
    
    q[0] = w
    q[1] = x
    q[2] = y
    q[3] = z
    
    return q


def hprod(q1, q2):
    """ Hamiltonian product of two quaternions """
    
    qprod = np.zeros(4)
    
    qprod[0] = q1[0]*q2[0] - q1[1]*q2[1] - q1[2]*q2[2] - q1[3]*q2[3]
    qprod[1] = q1[0]*q2[1] + q1[1]*q2[0] + q1[2]*q2[3] - q1[3]*q2[2]
    qprod[2] = q1[0]*q2[2] - q1[1]*q2[3] + q1[2]*q2[0] + q1[3]*q2[1]
    qprod[3] = q1[0]*q2[3] + q1[1]*q2[2] - q1[2]*q2[1] + q1[3]*q2[0]
    
    return qprod
    
    
def qconj(q):
    """ quaternion conjugate of q """
    
    qconj = np.zeros(4)
    qconj[0] = q[0]
    qconj[1] = -q[1]
    qconj[2] = -q[2]
    qconj[3] = -q[3]
    
    return qconj


def rand_rotate_vector(v):
    """
    Here the argument is v, a 3-vector in x,y,z space (e.g. the atomic positions
    of one of our atoms)
    
    The output is v_prime, another 3-vector, which is the rotated version of v
    """
    
    # generate a quaternion vector, with the first element zero
    # the last there elements are from v
    qv = np.zeros(4)
    qv[1:] = v.copy()
    
    # get a random quaternion vector
    q = rquaternion()
    
    # take the quaternion conjugated
    qconj = np.zeros(4)
    qconj[0] = q[0]
    qconj[1] = -q[1]
    qconj[2] = -q[2]
    qconj[3] = -q[3]
    
    q_prime = hprod( hprod(q, qv), qconj )
    
    v_prime = q_prime[1:].copy() # want the last 3 elements...
    
    return v_prime


def rand_rotate_molecule(xyzlist, rfloat=None):

    # get a random quaternion vector
    q = rquaternion(rfloat)
    print "quaternion:", q
    
    # take the quaternion conjugated
    qconj = np.zeros(4)
    qconj[0] = q[0]
    qconj[1] = -q[1]
    qconj[2] = -q[2]
    qconj[3] = -q[3]
    
    rotated_xyzlist = np.zeros(xyzlist.shape)
    qv = np.zeros(4)
    
    for i in range(xyzlist.shape[0]):
        
        qv[1:] = xyzlist[i,:].copy()
    
        q_prime = hprod( hprod(q, qv), qconj )
    
        rotated_xyzlist[i,:] = q_prime[1:].copy() # want the last 3 elements...
    
    return rotated_xyzlist
    
    
def simulate_shot(xyzlist, atomic_numbers, num_molecules, q_grid, rfloats=None):
    """
    Simulate a single x-ray scattering shot off an ensemble of identical
    molecules.
    
    Parameters
    ----------
    xyzlist : ndarray, float, 2d
        An n x 3 array of each atom's position in space
        
    atomic_numbers : ndarray, float, 1d
        An n-length list of the atomic numbers of each atom
        
    num_molecules : int
        The number of molecules to include in the ensemble.
        
    q_grid : ndarray, float, 2d
        An m x 3 array of the q-vectors corresponding to each detector position.
    
    Optional Parameters
    -------------------
    rfloats : ndarray, float, n x 3
        A bunch of random floats, uniform on [0,1] to be used to seed the 
        quaternion computation.
        
    Returns
    -------
    I : ndarray, float
        An array the same size as the first dimension of `q_grid` that gives
        the value of the measured intensity at each point on the grid.
    """
    
    I = np.zeros(q_grid.shape[0])
    
    for n in range(num_molecules):
        print "shooting molecule %d of %d" % (n+1, num_molecules)
        
        if rfloats == None:
            rotated_xyzlist = rand_rotate_molecule(xyzlist)
        else:
            rotated_xyzlist = rand_rotate_molecule(xyzlist, rfloats[n,:])
        
        for i,qvector in enumerate(q_grid):

            # compute the molecular form factor F(q)
            F = 0.0
            for j in range(xyzlist.shape[0]):
                fi = form_factor(qvector, atomic_numbers[j])
                r = rotated_xyzlist[j,:]
                
                #print "r:", r
                
                F1 = fi * np.exp( 1j * np.dot(qvector, r) )
                
                x = np.dot(qvector, r)
                #print "qsum:", ( np.cos(x) + 1j*np.sin(x) )
                
                F += fi * np.exp( 1j * np.dot(qvector, r) )
    
            I[i] += F.real*F.real + F.imag*F.imag

    return I


def plot_rotations():

    N = 1000

    # start with a unit vector in the x-directon
    v = np.zeros(3)
    v[0] = 1.0

    fig = plt.figure(figsize=(8,6), facecolor='w')
    ax = fig.add_subplot(111, projection='3d')

    for i in range(N):

        vp = rand_rotate_vector(v)

        x = vp[0]
        y = vp[1]
        z = vp[2]

        assert np.abs(norm(vp) - 1.0) < 0.00001

        ax.scatter(x,y,z)

    plt.show()

    return


    
if __name__ == '__main__':
    
    # if main, lets produce a text file for the simulated shot
    
    xyzQ = np.loadtxt('reference/512_atom_benchmark.xyz')
    xyzlist = xyzQ[:,:3]
    atomic_numbers = xyzQ[:,3].flatten()
    
    q_grid = np.loadtxt('reference/512_q.xyz')[:1]
    
    rfloats = np.loadtxt('reference/512_x_3_random_floats.txt')[:1]
    num_molecules = rfloats.shape[0]
    
    I = simulate_shot(xyzlist, atomic_numbers, num_molecules, q_grid, rfloats=rfloats)
    np.savetxt('simulated_shot_reference.dat', I)
    
    print 'SAVED: simulated_shot_reference.dat'
    
    
    