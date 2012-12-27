
"""
math.py

Various mathematical functions and operations.
"""

import logging
logging.basicConfig()
logger = logging.getLogger(__name__)

import multiprocessing as mp
from utils import parmap

import numpy as np
from random import randrange, seed

from scipy.signal import fftconvolve, convolve2d, correlate2d
from scipy.ndimage import filters
from scipy import ndimage


class CircularHough(object):
    """
    Methods for finding circles in images, using the Hough transform.
    
    This class is based on code from Andreas Skyman. Thanks Andreas for a job
    well done! (https://gitorious.org/hough-circular-transform)
    """
    
    def __init__(self, radii=10, threshold=0.001, stencil_width=1, procs='all'):
        """
        Initialize the class.
        
        radii : int OR list/ndarray of floats
            The radii at which to scan for circles. If an integer, will compute
            that number of equally spaced radii for the image -- a higher number
            yields more accurate detection at the expense of performance. If a
            list, will search at those radii indicated.
            
        threshold : float
            A number, in [0,1), that provides a lower bound on the features
            detected. Essentially filters out noise below this level. A higher
            number will remove false positives, but may result in false
            negatives.
            
        stencil_width : int
            The width, in pixel units, of the circular stencil used to match
            image features against. Bigger stencil yields less accurate results,
            but may allow more features to be found with fewer radii value
            evaluations.
            
        procs : int or str('all')
            The number of processors to run in parallel on. If set to 'all'
            (default), uses all available processors.
        """
        
        self.radii_parameter = radii
        self._threshold = threshold
        self._stencil_width = stencil_width
        self.edge_list = []
        
        # deal with the parallel settings
        if procs == 'all':
            self._procs = mp.cpu_count()
        elif type(procs) == int:
            self._procs = procs
        else:
            raise ValueError('Argument procs must be type int or str `all`')
            
        return
        
       
    def __call__(self, image, mode='all'):
        """
        Find circles in an image, using  the Circular Hough Transform (CHT).
        
        This function returns circle objects parameterized by their
        (radius, x_location, y_location). It should be fairly robust to noise,
        and provides some parameters for improving results in low or high
        noise environments.

        Parameters
        ----------
        image : ndarray, float
            A matrix representing the image.
            
        mode : str {'all', 'sharpest', 'concentric'}
            Whether to return all the found circles, only the sharpest one, or
            process the data as if it is a set of concentric circles.

        Returns
        -------
        circles : list of tuples OR tuple
            A list of tuples of the form (radius [float], x_location [int], 
            y_location [int]), where the x/y-location are indices of the matrix
            `image`. If `mode` == 'concentric', then just one tuple (x_location 
            [int], y_location [int]) gets returned.
        """
        
        self._image_shape = image.shape
        self._assert_sanity()
        
        temp_image = self._find_edges(image)
        self.edge_list = np.array(temp_image.nonzero())
        
        self.density = float(self.edge_list[0].size)/temp_image.size
        logger.debug("Signal density: %f" % self.density)
            
        self.accumulator = self._fft_Hough(temp_image)
            
        if mode.lower() == 'all':
            result = self._accumulator_maxima()
        elif mode.lower() == 'sharpest':
            result = self._global_accumulator_maxima()
        elif mode.lower() == 'concentric':
            result = self._concentric_maxima()
        else:
            raise ValueError("Argument `mode` must be one of {'all', 'sharpest', 'concentric'}")
            
        return result
        
        
    @property
    def radii(self):
        """
        Compute the radii computed.
        """
        if type(self.radii_parameter) == int:
            r = self._compute_radii(self.radii_parameter)
        elif (type(self.radii_parameter) == list) or (type(self.radii_parameter) == np.ndarray):
            r = np.array(self.radii_parameter)
        else:
            raise ValueError('Argument `radii` must be {int, list, np.ndarray}')
        return r
        
        
    def _compute_radii(self, num_radii):
        """
        Return a list of the radii to guess.
        """
        # this is just a guess, may need to be tweaked -- impossible to get
        # right in general
        max_possible_radius = float( min(self._image_shape) ) / 2.1
        mini = max_possible_radius / float(num_radii)
        return np.linspace(mini, max_possible_radius, num_radii)


    def _assert_sanity(self): 
        """
        Perform sanity checks on the parameters supplied in the function call.
        """
        
        max_diameter = min(self._image_shape)
        
        r_max = self.radii.max()
        r_min = self.radii.min()

        if 2*r_max >= max_diameter:
            raise ValueError("2*r_max must be < the image dimensions!")

        if r_min < 0.0:
            raise ValueError("r_min must be > 0")
        
        if self._threshold <= 0 or self._threshold >= 1:
            raise ValueError("threshold must be strictly between 0 and 1!")

        return
        
                    
    def _fft_Hough(self, edge_image):
        """
        Perform the Hough algorithm by convolving the edge-image with a
        circular stencil of the appropriate radius.
        
        Parameters
        ----------
        edge_image : ndarray, 
            The image, pre-filtered to find edges by an appropriate algorithm.
                        
        Returns
        -------
        acc : ndarray, float
            The Hough accumulator. The first dimension of this array is the
            accumulator for each radius evaluated.
        """

        logger.debug("Using fft-method...")
        
        radii = self.radii
        n_radii = len(self.radii)
        
        def compute_conv(i):
            """
            Multiprocessing helper function, computes the FFT-convolution and
            inserts the result into the accumulator array. Should be threadsafe.
            """
            r = radii[i]
            C = self._get_circle(r, self._stencil_width)
            result = fftconvolve(edge_image, C, 'same')
            acc[i*result.size:(i+1)*result.size] = result.flatten()
            return 0
            
        # if running in serial mode...
        if self._procs == 1:
            logger.debug('Running serial convolution loop...')
            acc = np.zeros( (radii.size, edge_image.shape[0], edge_image.shape[1]) )
            for i in range(n_radii):
                C = self._get_circle(radii[i], self._stencil_width)
                acc[i,:,:] = fftconvolve(edge_image, C, 'same')
                
        # else execute the parallel map
        else:
            acc = mp.Array( 'd', [0.0]*(radii.size * edge_image.shape[0] * edge_image.shape[1]) )
            logger.debug('launching parallel processes')            
            out = parmap( compute_conv, range(n_radii) )
            if not out == [0] * n_radii:
                raise RuntimeError('Process error in parallel execution of _fft_Hough()')
                
            acc = np.array(acc).reshape(radii.size, edge_image.shape[0], edge_image.shape[1])
            
        return acc
        

    def _get_circle(self, r, w=1):
        """
        Returns a circular kernel/stencil with the specified radius.
        
        Parameters
        ----------
        r : float
            The radius of the circle, in pixel units
        w : float
            The width of the circle, in pixel units
            
        Returns
        -------
        stencil : ndarray, int8
            A square array of the circular stencil. Each value of the array is
            one or zero.
        """

        if w > r:
            logger.warning("Width of annulus can't be > radius! (Using r...)")
            w = r

        grids = np.mgrid[-r:r+1, -r:r+1]
        template = grids[0]**2 + grids[1]**2
        large_circle = template <= r**2
        small_circle = template < (r - w)**2
        stencil = (large_circle - small_circle).astype(np.int8)
        
        return stencil
        

    def _find_edges(self, image):
        """ Method for handling selection of edge_filter and some more
            pre-processing. """

        image = filters.sobel(image, 0)**2 + filters.sobel(image, 1)**2 
        image -= image.min()

        image = image > image.max() * self._threshold

        # if self._threshold > 0:
        #     image = np.where(image > image.max()*self._threshold, image, 0)
        
        return image 
        
        
    def _accumulator_maxima(self, neighborhood_size=100, threshold=200):
        """
        Search the accumulator for maxima.
        """
        
        data_max = filters.maximum_filter(self.accumulator, neighborhood_size)
        maxima = (self.accumulator == data_max)
        data_min = filters.minimum_filter(self.accumulator, neighborhood_size)
        diff = ((data_max - data_min) > threshold)
        maxima[diff == 0] = 0

        labeled, num_objects = ndimage.label(maxima)
        logger.debug("Found: %d maxima" % num_objects)
        
        slices = ndimage.find_objects(labeled)
        max_points = list()
        for dy,dx,dz in slices:
            x_center = int( (dx.start + dx.stop - 1)/2 )
            y_center = int( (dy.start + dy.stop - 1)/2 )
            z_center = int( (dz.start + dz.stop - 1)/2 )
            max_points.append((x_center, y_center, z_center))
            
        return max_points
        
        
    def _global_accumulator_maxima(self):
        """
        Find the global maxima of the accumulator, representing the brightest
        circle.
        
        Returns:
        max_coordaintes : tuple
            (radius [float], x_location [int], y_location [int])
        """
        
        maxima = []
        max_positions = []
        
        # scan each radius value for maxima at that slice
        for i, r in enumerate(self.radii):
            max_positions.append(np.unravel_index(self.accumulator[i].argmax(), 
                                 self.accumulator[i].shape))
            maxima.append(self.accumulator[i].max())
            logger.debug("Maximum signal for radius %d: %d %s" % (r, maxima[i], max_positions[i]))

        # identify the max radius/coordinate combo
        max_index = np.unravel_index(self.accumulator.argmax(), self.accumulator.shape)
        max_coordaintes = (self.radii[max_index[0]], max_index[2], max_index[1])
        
        return max_coordaintes
        
        
    def _concentric_maxima(self):
        """
        If the image consists of one set of concentric rings, then each "slice" 
        of the accumulator for each radius value should have a maxima at the 
        same (x,y) point. Therefore we can effectively integrate out the radius
        dimension of the accumulator and look for the global maxima of the
        resultant 2D accumulator which should be the center of our concentric
        rings.
        
        Returns
        -------
        xy : tuple of ints
            The indices of the image estimated to be the center of the
            concentric rings.
        """
        flat_acc = self.accumulator.sum(axis=0) # sum over radial dim
        max_index = np.unravel_index(flat_acc.argmax(), flat_acc.shape)
        return max_index[::-1] # have to swap indices
        

def smooth(x, beta=10.0, window_size=11):
    """
    Apply a Kaiser window smoothing convolution.
    
    Parameters
    ----------
    x : ndarray
        The array to smooth.
    beta : float
        Parameter controlling the strength of the smoothing -- bigger beta 
        results in a smoother function.
    window_size : int
        The size of the Kaiser window to apply, i.e. the number of neighboring
        points used in the smoothing.
    """
    
    # make sure the window size is odd
    if window_size % 2 == 0:
        window_size += 1
    
    # apply the smoothing function
    s = np.r_[x[window_size-1:0:-1], x, x[-1:-window_size:-1]]
    w = np.kaiser(window_size, beta)
    y = np.convolve( w/w.sum(), s, mode='valid' )
    
    # remove the extra array length convolve adds
    b = (window_size-1) / 2
    smoothed = y[b:len(y)-b]
    
    return smoothed


def arctan3(y, x):
    """ like arctan2, but returns a value in [0,2pi] """
    theta = np.arctan2(y,x)
    theta[theta < 0.0] += 2 * np.pi
    return theta
    

def rand_pairs(numItems,numPairs):
	seed()
	i = 0
	pairs = []
	while i < numPairs:
		ind1 = randrange(numItems)
		ind2 = ind1
		while ind2 == ind1:
			ind2 = randrange(numItems)
		pair = [ind1,ind2]
		if pairs.count(pair) == 0:
			pairs.append(pair)
			i += 1
	return pairs


def fft_acf(data):
    '''
    Return the autocorrelation of a 1D array using the FFT
    Note: the result is normalized
    
    Parameters
    ----------
    data : ndarray, float, 1D
        Data to autocorrelate
        
    Returns
    -------
    acf : ndarray, float, 1D
        The autocorrelation function
    '''
    data = data - np.mean(data)
    result = signal.fftconvolve(data, data[::-1])
    result = result[result.size / 2:] 
    acf = result / result[0]
    return acf
    
    
