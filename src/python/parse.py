
"""
Various parsers:
-- CBF        (crystallographic binary format)
-- Kitty H5   (CXI pyana spinoff)
-- CXI        (coherent xray imaging format)
"""

import logging
logging.basicConfig()
logger = logging.getLogger(__name__)
# logger.setLevel('DEBUG')

import inspect
import tables
import re
import hashlib
import yaml
import tables
from base64 import b64encode

import numpy as np

# from odin import xray
from odin.math2 import find_center
from mdtraj import io


try:
    import fabio
    FABIO_IMPORTED = True
except ImportError as e:
    FABIO_IMPORTED = False


class CBF(object):
    """
    A class for parsing CBF files. Depends on fabio.
    
    NOTES ON GEOMETRY -- the geometry for different detectors is different.
    
    PILATUS 6M (SSRL 12-2)
    ----------------------
    Here, data are read out as a 2d array:
        slow: horizontal wrt lab frame / first array dim  / scans in y
        fast: vertical wrt lab frame   / second array dim / scans in x
    
    """
    
    def __init__(self, filename, mask=None, autocenter=True):
        """
        A light handle on a CBF file.
        
        Parameters
        ----------
        filename : str
            The path to the CBF file.
            
        mask : np.ndarray (dtype bool)
            Define a mask over the data. If `None` don't use a mask (default).
            Else should be a np array of dtype bool with the same shape as the
            intensities in the CBF file.
            
        autocenter : bool
            Whether or not to optimize the center (given a shot containing)
            diffuse rings.
        """
        
        if not FABIO_IMPORTED:
            raise ImportError('Could not import python package "fabio", please '
                              'install it')
        
        logger.info('Reading: %s' % filename)
        self.filename = filename
        self.autocenter = autocenter
        
        # extract all interesting stuff w/fabio
        self._fabio_handle = fabio.open(filename)
        self._info = self._fabio_handle.header
        self._parse_array_header( self._info['_array_data.header_contents'] )
        self.intensity_dtype = self._convert_dtype(self._info['X-Binary-Element-Type'])
            
            
        # interpret user provided mask
        if mask != None:
            if not mask.shape == self.intensities_shape:
                raise ValueError('`mask` must have same shape as intensity array '
                   '(%s), got: %s' % (str(self.intensities_shape), str(mask.shape)))
            self.mask = mask
        else:
            self.mask = None
            
            
        # add mask specific to the detector
        if self.detector_type.startswith('PILATUS 6M'):
            
            logger.info('Identified detector type as: PILATUS 6M')
            
            # add the default mask
            if self.mask == None:
                self.mask = self._pilatus_mask()
            else:
                self.mask *= self._pilatus_mask()
                
            # also, mask any negative pixels
            self.mask *= np.logical_not(self.intensities < 0.0)
            
        else:
            logger.debug('Unknown detector type: %s' % self._info['Detector'])
            
            
        logger.debug('Finished loading file')
        
        
    @property
    def md5(self):
        return self._info['Content-MD5']
    
        
    @property
    def intensities_shape(self):
        """
        Returns the shape (slow, fast)
        """
        shp = (int(self._info['X-Binary-Size-Second-Dimension']), 
               int(self._info['X-Binary-Size-Fastest-Dimension']))
        return shp
    
        
    @property
    def pixel_size(self):
        p = self._info['Pixel_size'].split()
        assert p[1].strip() == p[4].strip()
        assert p[2].strip() == 'x'
        pix_size = (float(p[0]), float(p[3]))
        return pix_size
    
        
    @property
    def path_length(self):
        # assume units are the same for all dims
        d, unit = self._info['Detector_distance'].split() 
        return float(d)
    
        
    @property
    def wavelength(self):
        return float(self._info['Wavelength'].split()[0])
    
        
    @property
    def polarization(self):
        return float(self._info['Polarization'])
    
        
    @property
    def center(self):
        """
        The center of the image, in PIXEL UNITS and as a tuple for dimensions
        (SLOW, FAST). Note that this is effectively (y,x), if y is the
        vertical direction in the lab frame.
        """
        if not hasattr(self, '_center'):
            self._center = self._find_center()
        return self._center
    
        
    @property
    def corner(self):
        """
        The bottom left corner position, in real space (x,y). Note that this
        corresponds to (FAST, SLOW) (!). This is the opposite of "center".
        """
        return (-self.pixel_size[1] * self.center[1], 
                -self.pixel_size[0] * self.center[0])
        
        
    @property
    def intensities(self):
        return self._fabio_handle.data
        
        
    @property
    def detector_type(self):
        return self._info['Detector:']


    def _convert_dtype(self, dtype_str):
        """
        Converts `dtype_str`, straight from the cbf file, to the right numpy
        dtype
        """
        
        # TJL: I'm just guessing the names for most of these....
        # the cbflib docs are useless!!
        conversions = {"signed 32-bit integer" : np.int32,
                       "unsigned 32-bit integer" : np.uint32,
                       "32-bit float" : np.float32,
                       "64-bit float" : np.float64}
        
        try:
            dtype = conversions[dtype_str]
        except KeyError as e:
            raise ValueError('Binary-Element-Type: %s has no know numpy '
                             'counterpart. Contact the dev team if you believe '
                             'this is wrong -- it may be an unexpected string.'
                             % dtype_str)
        
        return dtype
    
        
    def _parse_array_header(self, array_header):
        """
        Fabio provides an '_array_data.header_contents' key entry in that
        needs to be parsed. E.g. for a test PILATUS detector file generated at
        SSRL 12-2, this dictionary entry looks like
        
        fabio_object.header['_array_data.header_contents'] = 
        '# Detector: PILATUS 6M, S/N 60-0101 SSRL\r\n# 2012/Apr/09 20:02:10.800
        \r\n# Pixel_size 172e-6 m x 172e-6 m\r\n# Silicon sensor, thickness 0.00
        0320 m\r\n# Exposure_time 9.997700 s\r\n# Exposure_period 10.000000 s\r\
        n# Tau = 110.0e-09 s\r\n# Count_cutoff 1060885 counts\r\n# Threshold_set
        ting 6000 eV\r\n# N_excluded_pixels = 1685\r\n# Excluded_pixels: badpix_
        mask.tif\r\n# Flat_field: (nil)\r\n# Trim_directory: p6m0101_T8p0_vrf_m0
        p3_090729\r\n# Wavelength 0.7293 A\r\n# Energy_range (0, 0) eV\r\n# Dete
        ctor_distance 0.20000 m\r\n# Detector_Voffset 0.00000 m\r\n# Beam_xy (12
        31.50, 1263.50) pixels\r\n# Flux 0.0000 ph/s\r\n# Filter_transmission 1.
        0000\r\n# Start_angle 90.0000 deg.\r\n# Angle_increment 0.0100 deg.\r\n#
         Detector_2theta 0.0000 deg.\r\n# Polarization 0.990\r\n# Alpha 0.0000 d
        eg.\r\n# Kappa 0.0000 deg.\r\n# Phi 90.0000 deg.\r\n# Chi 0.0000 deg.\r
        \n# Oscillation_axis X, CW\r\n# N_oscillations 1'
        
        This function makes some sense of this mess.
        
        Parameters
        ----------
        array_header : str
            Something that looks like the dictionary value above.
        
        This function injects this information into self._info.
        """

        logger.debug('Reading header info...')

        items = array_header.split('#')
        
        for item in items:
            split = item.strip().split(' ')
            if len(split) > 1:
                k = split[0].strip().lstrip(':')
                self._info[k] = ' '.join(split[1:]).strip().lstrip('=')
        
        return
    

    def _check_md5(self):
        """
        Check the data are intact by computing the md5 checksum of the binary
        data, and comparing it to an analagous md5 computed when the file was
        generated.
        """
        
        # This is a cute idea but I have no idea what data the md5 is performed
        # on, or how to retrieve that data from the file. This function is
        # currently broken (close to working)
        
        md5 = hashlib.md5()
        md5.update(self.intensities.flatten().tostring()) # need to feed correct data in here...
        data_md5 = b64encode(md5.digest())
        if not md5.hexdigest() == self.md5:
            logger.critical("Data MD5:    %s" % data_md5)
            logger.critical("Header MD5:  %s" % self.md5)
            raise RuntimeError('Data and stored md5 hashes do not match! Data corrupted.')
    
            
    def _find_center(self):
        """
        Find the center of any Bragg rings (aka the location of the x-ray beam).
        
        Returns
        -------
        center : tuple of ints
            The indicies of the pixel nearest the center of the Bragg peaks. The
            center is returned in pixel units in terms of (slow, fast).
            
        See Also
        --------
        self.center
        self.corner
        """
        if self.autocenter:
            center = find_center(self.intensities, mask=self.mask, pix_res=0.01)
        else:
            center = np.array(self.intensities_shape) / 2.0
        return center
    
        
    def _pilatus_mask(self, border_size=3):
        """
        The pixels on the edges of the detector are often noisy -- this function
        provides a way to mask both the gaps and these border pixels.

        Parameters
        ----------
        border_size : int
            The size of the border (in pixels) with which to extend the mask
            around the detector gaps.
        """

        border_size = int(border_size)
        mask = np.ones(self.intensities_shape, dtype=np.bool)

        # below we have the cols (x_gaps) and rows (y_gaps) to mask
        # these mask the ASIC gaps

        x_gaps = [(194-border_size,  212+border_size),
                  (406-border_size,  424+border_size),
                  (618-border_size,  636+border_size),
                  (830-border_size,  848+border_size),
                  (1042-border_size, 1060+border_size),
                  (1254-border_size, 1272+border_size),
                  (1466-border_size, 1484+border_size),
                  (1678-border_size, 1696+border_size),
                  (1890-border_size, 1908+border_size),
                  (2102-border_size, 2120+border_size),
                  (2314-border_size, 2332+border_size)]
                  
        y_gaps = [(486-border_size,  494+border_size),
                  (980-border_size,  988+border_size),
                  (1474-border_size, 1482+border_size),
                  (1968-border_size, 1976+border_size)]

        for x in x_gaps:
            mask[x[0]:x[1],:] = np.bool(False)

        for y in y_gaps:
            mask[:,y[0]:y[1]] = np.bool(False)
        
            
        # we also mask the beam stop for 12-2...
        mask[1200:1325,1164:] = np.bool(False)

        return mask

        
    # def as_shotset(self):
    #     """
    #     Convert the CBF file to an ODIN shotset representation.
    #     
    #     Returns
    #     -------
    #     cbf : odin.xray.Shotset
    #         The CBF file as an ODIN shotset.
    #     """
    #     
    #     p = np.array(list(self.corner) + [self.path_length])
    #     f = np.array([self.pixel_size[0], 0.0, 0.0]) # fast is x
    #     s = np.array([0.0, self.pixel_size[1], 0.0]) # slow is y
    #     
    #     bg = xray.BasisGrid()
    #     bg.add_grid(p, s, f, self.intensities_shape)
    #     
    #     # todo better value for photons
    #     b = xray.Beam(1e4, wavelength=self.wavelength) 
    #     d = xray.Detector(bg, b.k)
    #     s = xray.Shotset(self.intensities.flatten().astype(np.float64), d, self.mask)
    #     
    #     return s
    # 
    #     
    # @classmethod
    # def files_to_shotset(cls, list_of_cbf_files, shotset_filename=None,
    #                      autocenter=True):
    #     """
    #     Convert a bunch of CBF files to a single ODIN shotset instance. If you 
    #     write the shotset immediately to disk, does this in a smart "lazy" way 
    #     so as to preseve memory.
    #     
    #     Parameters
    #     ----------
    #     list_of_cbf_files : list of str
    #         A list of paths to CBF files to convert.
    #     
    #     Optional Parameters
    #     -------------------
    #     shotset_filename : str
    #         The filename of the shotset to write to disk.
    #         
    #     autocenter : bool
    #         Whether or not to automatically determine the center of the detector.
    #         
    #     Returns
    #     -------
    #     ss : odin.xray.Shotset
    #         If `shotset_filename` is None, then returns the shotset object
    #     """
    #     
    #     # convert one CBF, and use it to get the detector, etc info
    #     seed_shot = cls(list_of_cbf_files[0], autocenter=autocenter).as_shotset()
    #     
    #     if shotset_filename:
    #         logger.info('writing CBF files straight to disk at: %s' % shotset_filename)
    #         
    #         seed_shot.save(shotset_filename)
    #         
    #         # now open a handle to that h5 file and add to it
    #         for i,fn in enumerate(list_of_cbf_files[1:]):
    #              
    #             # i+1 b/c we already saved one shot
    #             d = {('shot%d' % (i+1,)) : cls(fn, autocenter=False).intensities.flatten()}
    #             io.saveh( shotset_filename, **d )
    #             
    #         io.saveh( shotset_filename, num_shots=np.array([ len(list_of_cbf_files) ]) )
    #         logger.info('Combined CBF data into: %s' % shotset_filename)
    #         return
    # 
    #     else:
    #         shot_i = np.zeros(( len(list_of_cbf_files), seed_shot.intensities.shape[1] ))
    #         shot_i[0,:] = seed_shot.intensities.flatten()
    #         
    #         for i,fn in enumerate(list_of_cbf_files[1:]):
    #             x = cls(fn, autocenter=False).intensities.flatten()
    #             if not len(x) == shot_i.shape[1]:
    #                 raise ValueError('Variable number of pixels in shots!')
    #             shot_i[i+1,:] = x
    #         
    #         ss = xray.Shotset( shot_i, seed_shot.detector, seed_shot.mask )
    # 
    #         return ss
    #         
    #         
    # @classmethod
    # def files_to_rings(cls, list_of_cbf_files, q_values, num_phi,
    #                    autocenter=True):
    #     """
    #     Convert a bunch of CBF files to a single ODIN rings instance.
    # 
    #     Parameters
    #     ----------
    #     list_of_cbf_files : list of str
    #         A list of paths to CBF files to convert.
    #         
    #     q_values : ndarray, float
    #         A one-D array containing the |q| values (in inverse Angstroms) that
    #         you want to convert
    # 
    #     Optional Parameters
    #     -------------------
    #     num_phi : int
    #         The number of points around each ring to interpolate.
    #     
    #     shotset_filename : str
    #         The filename of the shotset to write to disk.
    # 
    #     autocenter : bool
    #         Whether or not to automatically determine the center of the detector.
    # 
    #     Returns
    #     -------
    #     rings : odin.xray.Rings
    #         If `rings_filename` is None, then returns the shotset object
    #     """
    #     
    #     # save the center from one so we don't have to compute it for all
    #     seed_cbf = cls(list_of_cbf_files[0], autocenter=autocenter)
    #     center = seed_cbf.center.copy()
    #     
    #     
    #     seed_ss = seed_cbf.as_shotset()
    #     seed_ring = seed_ss.to_rings(q_values, num_phi=num_phi)
    #     
    #     
    #     for cbf_file in list_of_cbf_files[1:]:
    #         cbf = cls(cbf_file, autocenter=False)
    #         cbf._center = center
    #         ss = cbf.as_shotset()
    #         r  = ss.to_rings(q_values, num_phi=num_phi)
    #         seed_ring.append(r)
    #         
    # 
    #     return seed_ring
    
        
class CXIdb(object):
    """
    Base class for CXIdb file objects. Will likely need to be subclassed to be
    useful in any real-world context.
    """
    
    def _get_groups(self, name, root='/'):
        """
        Locates groups in the HDF5 file structure, beneath `root`, with name
        matching `name`.
        
        Returns
        -------
        groups : list
            A list of pytables group objects
        """
        groups = []
        for g in self._fhandle.walkGroups(root):                
            gname = g.__str__().split('/')[-1].split()[0]
            if gname.find(name) == 0:
                groups.append(g)
        return groups


    def _get_nodes(self, name, root='/', strict=False):
        """
        Locates nodes in the HDF5 file structure, beneath `root`, with name
        matching `name`.

        Returns
        -------
        nodes : list
            A list of pytables nodes objects
        """
        nodes = []
        for n in self._fhandle.walkNodes(root):                
            nname = n.__str__().split('/')[-1].split()[0]
            if not isinstance(n, tables.link.SoftLink):
                if strict:
                    if nname == name:
                        nodes.append(n)
                else:
                    if nname.find(name) == 0:
                        nodes.append(n)
        return nodes
    

class CheetahCXI(CXIdb):
    """
    A parser for the CXIdb files generated by cheetah at LCLS.
    """
    
    def __init__(self, filename):
        
        if not filename.endswith('.cxi'):
            raise IOError('Can only read .cxi files, got: %s' % filename)
        
        self._fhandle = tables.File(filename, 'r')
        self._ds1_data = self._fhandle.root.entry_1.instrument_1.detector_1.data

        return
    

    def close(self):
        self._fhandle.close()
        return
    
        
    @property
    def num_shots(self):
        return self._ds1_data.shape[0]
    

    def energy(self, mean=True):
        """
        Returns the energy in eV.

        Parameters
        ----------
        mean : bool
            Return the mean. If `False`, returns the measured energy for each
            shot.
        """
        n = self._get_nodes('photon_energy_eV', strict=True)[0]
        if mean:
            return n.read().mean()
        else:
            return n.read()
    

    def shot(self, shot_number, detector='ds1'):
        """
        Read the intensity data for a single shot.

        Parameters
        ----------
        shot_number : int
            Which shot to read.

        detector : str
            Which detector to read the data for.

        Returns
        -------
        shot_data : np.ndarray
            An array of intensity data. The first dimension indexes shots, the
            next two are a single image in cheetah's CSPAD format.
        """
        if detector == 'ds1':
            return self._ds1_data.read(shot_number)
        else:
            raise NotImplementedError('only ds1 support in right now')
    

    def shot_range(self, start, stop, detector='ds1'):
        """
        Read a range of shots.

        Parameters
        ----------
        start : int
            Shot to start at (zero indexed).

        stop : int
            Where to stop.

        detector : str
            Which detector to read the data for.

        Returns
        -------
        shot_data : np.ndarray
            An array of intensity data. The first dimension indexes shots, the
            next two are a single image in cheetah's CSPAD format.
        """
        if detector == 'ds1':
            return self._ds1_data.read(start, stop)
        else:
            raise NotImplementedError('only ds1 support in right now')
    

    def shot_iterator(self, detector='ds1'):
        """
        Return an iterable that enables looping over shot data on disk. This
        object lets python access shots one at a time without loading all of
        them into memory. Yields data in Odin format!

        Parameters
        ----------
        detector : str
            Which detector to read the data for.

        Returns
        -------
        shotiter : tables.earray.EArray
            An iterable element array .
        """

        if detector == 'ds1':
            return self._ds1_data.iterrows()
        else:
            raise NotImplementedError('only ds1 support in right now')
    
    
    @staticmethod
    def cheetah_instensities_to_odin(intensities):

        if not intensities.shape == (1480, 1552):
            raise ValueError('`intensities` argument array incorrect shape! Must be:'
                             ' (1480, 1552), got %s.' % str(intensities.shape))

        flat_intensities = np.zeros(1480 * 1552, dtype=intensities.dtype)

        for q in range(4):
            for twoXone in range(8):

                # extract the cheetah intensities
                x_start = 388 * q
                x_stop = 388 * (q+1)

                y_start = 185 * twoXone
                y_stop = 185 * (twoXone + 1)

                # each sec is a ASIC, both belong to the same 2x1
                sec1, sec2 = np.hsplit(intensities[y_start:y_stop,x_start:x_stop], 2)

                # determine the positions of the flat array to put intens data in
                n_ASIC_pixels = 185 * 194
                flat_start = (q * 8 + twoXone) * (n_ASIC_pixels * 2) # 2x1 index X px in 2x1

                # inject them into the Odin array
                flat_intensities[flat_start:flat_start+n_ASIC_pixels] = sec1.flatten()
                flat_intensities[flat_start+n_ASIC_pixels:flat_start+n_ASIC_pixels*2] = sec2.flatten()

        return flat_intensities

