#! /usr/bin/env python

import os
import shutil
import sys
import time
import types
import numpy as N
import pyfits
import ccos
from calcosparam import *       # parameter definitions

# initial value
verbosity = VERBOSE

# for appending to a trailer file
fd_trl = None

def writeOutputEvents (infile, outfile):
    """
    This function creates a recarray object with the column definitions
    appropriate for a corrected time-tag table, reads an input events table
    into this object, and writes it to the output file.  If the input file
    contains a GTI table, that will be copied unchanged to output.

    argument:
    infile         name of the input FITS file containing an EVENTS table
                   and optionally a GTI table
    outfile        name of file for output EVENTS table (and GTI table)
    """

    # ifd = pyfits.open (infile, mode="readonly", memmap=1)
    ifd = pyfits.open (infile, mode="readonly")
    events_extn = ifd["EVENTS"]
    indata = events_extn.data
    if indata is None:
        nrows = 0
    else:
        nrows = indata.shape[0]
    detector = ifd[0].header.get ("detector", "FUV")
    tagflash = (ifd[0].header.get ("tagflash", default="NONE") != "NONE")

    # Create the output events HDU.
    hdu = createCorrtagHDU (nrows, detector, events_extn.header)

    if nrows == 0:
        primary_hdu = pyfits.PrimaryHDU (header=ifd[0].header)
        ofd = pyfits.HDUList (primary_hdu)
        updateFilename (ofd[0].header, outfile)
        ofd.append (hdu)
        if len (ifd) == 3:
            ofd.append (ifd["GTI"])
        ofd.writeto (outfile)
        ifd.close()
        return nrows

    outdata = hdu.data

    # Copy data from the input table to the output HDU object.

    outdata.field ("TIME")[:] = indata.field ("TIME")

    outdata.field ("RAWX")[:] = indata.field ("RAWX")
    outdata.field ("RAWY")[:] = indata.field ("RAWY")
    outdata.field ("XCORR")[:] = indata.field ("RAWX")
    outdata.field ("YCORR")[:] = indata.field ("RAWY")

    outdata.field ("XDOPP")[:] = N.zeros (nrows, dtype=N.float32)
    outdata.field ("XFULL")[:] = N.zeros (nrows, dtype=N.float32)
    outdata.field ("YFULL")[:] = N.zeros (nrows, dtype=N.float32)

    outdata.field ("EPSILON")[:] = N.ones (nrows, dtype=N.float32)
    outdata.field ("DQ")[:] = N.zeros (nrows, dtype=N.int16)
    if detector == "FUV":
        outdata.field ("PHA")[:] = indata.field ("PHA")
    else:
        outdata.field ("PHA")[:] = 255

    primary_hdu = pyfits.PrimaryHDU (header=ifd[0].header)
    ofd = pyfits.HDUList (primary_hdu)
    updateFilename (ofd[0].header, outfile)
    ofd.append (hdu)

    # GTI table.
    if len (ifd) == 3:
        ofd.append (ifd["GTI"])

    ofd.writeto (outfile)
    ifd.close()

    return nrows

def createCorrtagHDU (nrows, detector, header):
    """Create the output events HDU.

    @param nrows: number of rows to allocate (may be zero)
    @type nrows: int
    @param detector: FUV or NUV
    @type detector: string
    @param header: events extension header
    @type header: pyfits Header object

    @return: header/data unit for a corrtag table
    @rtype: pyfits BinTableHDU object
    """

    col = []
    col.append (pyfits.Column (name="TIME", format="1E", unit="s"))
    col.append (pyfits.Column (name="RAWX", format="1I", unit="pixel"))
    col.append (pyfits.Column (name="RAWY", format="1I", unit="pixel"))
    col.append (pyfits.Column (name="XCORR", format="1E", unit="pixel"))
    col.append (pyfits.Column (name="YCORR", format="1E", unit="pixel"))
    col.append (pyfits.Column (name="XDOPP", format="1E", unit="pixel"))
    col.append (pyfits.Column (name="XFULL", format="1E", unit="pixel"))
    col.append (pyfits.Column (name="YFULL", format="1E", unit="pixel"))
    col.append (pyfits.Column (name="EPSILON", format="1E"))
    col.append (pyfits.Column (name="DQ", format="1I"))
    col.append (pyfits.Column (name="PHA", format="1B"))
    cd = pyfits.ColDefs (col)

    hdu = pyfits.new_table (cd, header=header, nrows=nrows)

    return hdu

def dummyGTI (exptime):
    """Return a GTI table.

    @param exptime: exposure time in seconds
    @type exptime: float

    @return: header/data unit for a GTI table covering the entire exposure
    @rtype: pyfits BinTableHDU object
    """

    col = []
    col.append (pyfits.Column (name="START", format="1D", unit="s"))
    col.append (pyfits.Column (name="STOP", format="1D", unit="s"))
    cd = pyfits.ColDefs (col)
    hdu = pyfits.new_table (cd, nrows=1)
    hdu.header.update ("extname", "GTI")
    outdata = hdu.data
    outdata.field ("START")[:] = 0.
    outdata.field ("STOP")[:] = exptime

    return hdu

def returnGTI (infile):
    """Return a list of (start, stop) good time intervals.

    arguments:
    infile         name of the input FITS file containing a GTI table
    """

    fd = pyfits.open (infile, mode="readonly")
    if len (fd) < 3:
        fd.close()
        gti = []
        return gti

    indata = fd["GTI"].data
    if indata is None:
        gti = []
    else:
        nrows = indata.shape[0]
        start = indata.field ("START")
        stop = indata.field ("STOP")
        gti = [(start[i], stop[i]) for i in range (nrows)]

    return gti

def findColumn (table, colname):
    """Return True if colname is found (case-insensitive) in table.

    @param table: name of table or data block for a FITS table
    @type table: string (if name of table) or FITS record object
    @param colname: name to test for existence in table
    @type colname: string

    @return: True if colname is in the table (without regard to case)
    @rtype: boolean
    """

    if type (table) is str:
        fd = pyfits.open (table, mode="readonly")
        fits_rec = fd[1].data
        fd.close()
    else:
        fits_rec = table

    names = []
    for name in fits_rec.names:
        names.append (name.lower())

    if colname.lower() in names:
        return True
    else:
        return False

def getTable (table, filter, exactly_one=False, at_least_one=False):
    """Return the data portion of a table.

    All rows that match the filter (a dictionary of column_name = value)
    will be returned.  If the value in the table is STRING_WILDCARD or
    INT_WILDCARD (depending on the data type of the column), that value
    does match the filter for that column.  Also, for a given filter key,
    if the value of the filter is STRING_WILDCARD or NOT_APPLICABLE,
    the test on filter will not be applied for that key (i.e. that filter
    element matches any row).

    It is an error if exactly_one or at_least_one is true but no row
    matches the filter.  A warning will be printed if exactly_one is true
    but more than one row matches the filter.

    arguments:
    table          name of the reference table
    filter         dictionary; each key is a column name, and if the value
                   in that column matches the filter value for some row,
                   that row will be included in the set that is returned
    exactly_one    true if there must be one and only one matching row
    at_least_one   true if there must be at least one matching row
    """

    # fd = pyfits.open (table, mode="readonly", memmap=1)
    fd = pyfits.open (table, mode="readonly")
    data = fd[1].data

    # There will be one element of select_arrays for each non-trivial
    # selection criterion.  Each element of select_arrays is an array
    # of flags, true if the row matches the criterion.
    select_arrays = []
    for key in filter.keys():

        if filter[key] == STRING_WILDCARD or \
           filter[key] == NOT_APPLICABLE:
            continue
        column = data.field (key)
        selected = (column == filter[key])

        # Test for for wildcards in the table.
        wild = None
        if isinstance (column, N.chararray):
            wild = (column == STRING_WILDCARD)
        #elif isinstance (column[0], N.integer):
        #    wild = (column == INT_WILDCARD)
        if wild is not None:
            selected = N.logical_or (selected, wild)

        select_arrays.append (selected)

    if len (select_arrays) > 0:
        selected = select_arrays[0]
        for sel_i in select_arrays[1:]:
             selected = N.logical_and (selected, sel_i)
        newdata = data[selected]
    else:
        newdata = fd[1].data.copy()

    fd.close()

    nselect = len (newdata)
    if nselect < 1:
        newdata = None

    if (exactly_one or at_least_one) and nselect < 1:
        message = "Table has no matching row;\n" + \
                  "table name is " + table + "\n" + \
                  "row selection is " + repr (filter)
        raise RuntimeError, message

    if exactly_one and nselect > 1:
        printWarning ("Table has more than one matching row;")
        printContinuation ("table name is " + table)
        printContinuation ("row selection is " + repr (filter))
        printContinuation ("only the first will be used.")

    return newdata

def getColCopy (filename="", column=None, extension=1, data=None):
    """Return the specified column in native format.

    @param filename: the name of the FITS file
    @type filename: string
    @param column: column name or number
    @type column: string or integer
    @param extension: number of extension containing the table
    @type extension: integer
    @param data: the data portion of a table
    @type data: pyfits record object

    @return: the column data
    @rtype: array

    Specify either the name of the file or the data block, but not both.
    """

    if filename and data is not None:
        raise RuntimeError, "Specify either filename or data, but not both."

    if filename:
        fd = pyfits.open (filename, mode="readonly")
        temp = fd[extension].data.field (column)
        fd.close()
    elif data is not None:
        temp = data.field (column)
    else:
        raise RuntimeError, "Either filename or data must be specified."

    x = N.empty (temp.shape, dtype=temp.dtype.type)
    x[...] = temp

    return x

def getTemplate (raw_template, x_offset, nelem):
    """Return the template spectrum embedded in a possibly larger array.

    @param raw_template: template spectrum as read from the lamptab
    @type raw_template: numpy array
    @param x_offset: offset of raw_template in the extended template
    @type x_offset: int
    @param nelem: length of template spectrum to return
    @type nelem: int
    """

    len_raw = len (raw_template)

    if x_offset == 0 and nelem == len_raw:
        return raw_template.copy()

    template = N.zeros (nelem, dtype=raw_template.dtype)
    template[x_offset:len_raw+x_offset] = raw_template

    return template

def getHeaders (input):
    """Return a list of all the headers in the file.

    argument:
    input       name of an input file
    """

    fd = pyfits.open (input, mode="readonly")

    headers = [hdu.header.copy() for hdu in fd]

    fd.close()

    return headers

def timeAtMidpoint (info):
    """Return the time (MJD) at the midpoint of an exposure.

    argument:
    info          dictionary of header keywords (or could be a Header object)
    """
    return (info["expstart"] + info["expend"]) / 2.

def evalDisp (x, coeff, delta=0.):
    """Evaluate the dispersion relation at x.

    The function value will be the wavelength (or array of wavelengths) at x,
    in Angstroms.

    @param x: pixel coordinate (or array of coordinates)
    @type x: numpy array or float
    @param coeff: array of polynomial coefficients which convert pixel number
        to wavelength in Angstroms
    @type coeff: sequence object (e.g. numpy array)
    @param delta: offset to subtract from pixel coordinate
    @type delta: float

    @return: wavelength (or array of wavelengths) at x
    @rtype: numpy array or float
    """

    ncoeff = len (coeff)
    if ncoeff < 2:
        raise ValueError, "Dispersion relation has too few coefficients"

    x_prime = x - delta

    sum = coeff[ncoeff-1]
    for i in range (ncoeff-2, -1, -1):
        sum = sum * x_prime + coeff[i]

    return sum

def evalDerivDisp (x, coeff, delta=0.):
    """Evaluate the derivative of the dispersion relation at x.

    The function value will be the slope (or array of slopes) at x,
    in Angstroms per pixel.

    @param x: pixel coordinate (or array of coordinates)
    @type x: numpy array or float
    @param coeff: array of polynomial coefficients which convert pixel number
        to wavelength in Angstroms
    @type coeff: sequence object (e.g. numpy array)
    @param delta: offset to subtract from pixel coordinate
    @type delta: float

    @return: slope at x, in Angstroms per pixel
    @rtype: numpy array or float
    """

    ncoeff = len (coeff)
    if ncoeff < 2:
        raise ValueError, "Dispersion relation has too few coefficients"

    x_prime = x - delta

    sum = (ncoeff-1.) * coeff[ncoeff-1]
    for n in range (ncoeff-2, 0, -1):
        sum = sum * x_prime + n * coeff[n]

    return sum

def evalInvDisp (wavelength, coeff, delta=0., tiny=1.e-8):
    """Evaluate the inverse of the dispersion relation at wavelength.

    The function value will be the pixel number (or array of pixel numbers)
    at the specified wavelength(s).  Newton's method is used for finding
    the pixel numbers, and the iterations are stopped when the largest
    difference between the specified wavelengths and computed wavelengths
    is less than tiny.

    @param wavelength: wavelength (or array of wavelengths)
    @type wavelength: numpy array or float
    @param coeff: array of polynomial coefficients which convert pixel number
        to wavelength in Angstroms
    @type coeff: sequence object (e.g. numpy array)
    @param delta: offset to subtract from pixel coordinate
    @type delta: float
    @param tiny: maximum allowed difference between the final pixel number(s)
        and the value from the previous iteration
    @type tiny: float

    @return: pixel number (or array of pixel numbers) at wavelength
    @rtype: numpy array or float
    """

    tiny = abs (tiny)

    # initial value
    try:
        nelem = len (wavelength)
        x = N.arange (nelem, dtype=N.float64)
    except TypeError:
        nelem = 0
        x = 0.

    # Iterate to find the pixel number(s) x such that evaluating the
    # dispersion relation at that point gives the actual wavelength
    # at the first pixel.
    done = 0
    while not done:
        if nelem > 0:
            x_prev = x.copy()
        else:
            x_prev = x
        wl = evalDisp (x, coeff, delta)
        slope = evalDerivDisp (x, coeff, delta)
        wl_diff = wavelength - wl
        x += wl_diff / slope
        diff = N.abs (x - x_prev)
        if diff.max() < tiny:
            done = 1

    return x

def geometricDistortion (x, y, geofile, segment, igeocorr):
    """Apply geometric (INL) correction.

    x, y          arrays of pixel coordinates of events
    geofile       name of geometric correction reference file
    segment       FUVA or FUVB
    igeocorr      "PERFORM" if interpolation should be used within the geofile
    """

    fd = pyfits.open (geofile, mode="readonly", memmap=0)
    # fd = pyfits.open (geofile, mode="readonly", memmap=1)
    x_hdu = fd[(segment,1)]
    y_hdu = fd[(segment,2)]

    origin_x = x_hdu.header.get ("origin_x", 0)
    origin_y = x_hdu.header.get ("origin_y", 0)

    if origin_x != y_hdu.header.get ("origin_x", 0) or \
       origin_y != y_hdu.header.get ("origin_y", 0):
        raise RuntimeError, "Inconsistent ORIGIN_X or _Y keywords in GEOFILE"

    xbin = x_hdu.header.get ("xbin", 1)
    ybin = x_hdu.header.get ("ybin", 1)
    if xbin != y_hdu.header.get ("xbin", 1) or \
       ybin != y_hdu.header.get ("ybin", 1):
        raise RuntimeError, "Inconsistent XBIN or YBIN keywords in GEOFILE"

    interp_flag = (igeocorr == "PERFORM")
    ccos.geocorrection (x, y, x_hdu.data, y_hdu.data, interp_flag,
                origin_x, origin_y, xbin, ybin)

    fd.close()

def activeArea (segment, brftab):
    """Return the limits of the FUV active area.

    @param segment: for finding the appropriate row in the brftab
    @type segment: string
    @param brftab: name of the baseline reference frame table (ignored for NUV)
    @type brftab: string
    @return: the low and high limits and the left and right limits of the
        active area of the detector.  For NUV this will be (0, 1023, 0, 1023).
    @rtype: tuple
    """

    if segment[0] == "N":
        return (0, NUV_Y-1, 0, NUV_X-1)

    brf_info = getTable (brftab, {"segment": segment}, exactly_one=True)

    a_low = brf_info.field ("a_low")[0]
    a_high = brf_info.field ("a_high")[0]
    a_left = brf_info.field ("a_left")[0]
    a_right = brf_info.field ("a_right")[0]

    return (a_low, a_high, a_left, a_right)

def getInputDQ (input):
    """Return the data quality array, or an array of zeros.

    If the data quality extension (EXTNAME = "DQ", EXTVER = 1) actually has
    a non-null data portion, that data array will be returned.  If the data
    portion is null (NAXIS = 0), a constant array will be returned; in this
    case the size will be taken from keywords NPIX1 and NPIX2, and the data
    value will be the value of the PIXVALUE keyword.

    argument:
    input         name of a FITS file containing an image set (SCI, ERR, DQ);
                  only the DQ extension will be read
    """

    fd = pyfits.open (input, mode="readonly")

    hdr = fd[("DQ",1)].header
    detector = fd[0].header["detector"]
    obsmode = fd[0].header["obsmode"]

    # this section for npix and x_offset is based on getinfo.getGeneralInfo
    if detector == "FUV":
        npix = (FUV_Y, FUV_EXTENDED_X)
        x_offset = FUV_X_OFFSET
    else:
        if obsmode == "IMAGING":
            npix = (NUV_Y, NUV_X)
            x_offset = 0
        else:
            npix = (NUV_Y, NUV_EXTENDED_X)
            x_offset = NUV_X_OFFSET

    # Does the data portion exist?
    if hdr["naxis"] > 0:
        if fd[("DQ",1)].data.shape[1] == npix[1]:
            dq_array = fd[("DQ",1)].data
            # undo the flagging of regions outside subarrays
            dq_array = N.bitwise_and (dq_array, 16383-(64+128))
        else:
            dq_array = N.zeros (npix, dtype=N.int16)
            dq_array[:,x_offset:len_raw+x_offset] = fd[("DQ",1)].data
    else:
        dq_array = N.zeros (npix, dtype=N.int16)
        if hdr.has_key ("pixvalue"):
            pixvalue = hdr["pixvalue"]
            if pixvalue != 0:
                dq_array[:,:] = pixvalue

    fd.close()

    return dq_array

def minmaxDoppler (info, doppcorr, doppmag, doppzero, orbitper):
    """Compute the range of Doppler shifts.

    @param info: keywords and values
    @type info: dictionary
    @param doppcorr: if doppcorr = "PERFORM", shift DQ positions to track
        Doppler shift during exposure
    @type doppcorr: string
    @param doppmag: magnitude (pixels) of Doppler shift
    @type doppmag: int or float
    @param doppzero: time (MJD) when Doppler shift is zero and increasing
    @type doppzero: float
    @param orbitper: orbital period (s) of HST
    @type orbitper: float

    @return: minimum and maximum Doppler shifts (will be 0 if doppcorr is omit)
    @rtype: tuple
    """

    if doppcorr == "PERFORM":
        expstart = info["expstart"]
        exptime  = info["exptime"]
        axis = 2 - info["dispaxis"]     # 1 --> 1,  2 --> 0

        # time is the time in seconds since doppzero.
        nelem = int (round (exptime))           # one element per sec
        nelem = max (nelem, 1)
        time = N.arange (nelem, dtype=N.float64) + \
                   (expstart - doppzero) * SEC_PER_DAY

        # shift is in pixels (wavelengths increase toward larger pixel number).
        shift = -doppmag * N.sin (2. * N.pi * time / orbitper)
        mindopp = shift.min()
        maxdopp = shift.max()
    else:
        mindopp = 0.
        maxdopp = 0.

    return (mindopp, maxdopp)

def updateDQArray (bpixtab, info, dq_array,
                   minmax_shifts, minmax_doppler):
    """Apply the data quality initialization table to DQ array.

    dq_array is a 2-D array, to be written as the DQ extension in an
    ACCUM file (_counts or _flt).  Its contents are assumed to be valid
    on input, since it may have been read from the raw file (if the
    input was an ACCUM image), and it may therefore include flagged
    pixels.  The flag information in the bpixtab will be combined
    (in-place) with dq_array using bitwise OR.

    @param bpixtab: name of the data quality initialization table
    @type bpixtab: string
    @param info: keywords and values
    @type info: dictionary
    @param dq_array: data quality image array (modified in-place)
    @type dq_array: numpy array
    @param minmax_shifts: the min and max offsets in the dispersion direction
        and the min and max offsets in the cross-dispersion direction during
        the exposure
    @type minmax_shifts: tuple
    @param minmax_doppler: minimum and maximum Doppler shifts (will be 0 if
        doppcorr is omit)
    @type minmax_doppler: tuple
    """

    dq_info = getTable (bpixtab, filter={"segment": info["segment"]})
    if dq_info is None:
        return

    (min_shift1, max_shift1, min_shift2, max_shift2) = minmax_shifts
    (mindopp, maxdopp) = minmax_doppler

    # Update the 2-D data quality extension array from the DQI table info.
    lx = dq_info.field ("lx")
    ly = dq_info.field ("ly")
    dx = dq_info.field ("dx")
    dy = dq_info.field ("dy")
    ux = lx + dx - 1
    uy = ly + dy - 1
    if max_shift1 >= 0:
        lx -= int (round (max_shift1))
        ux -= int (round (min_shift1))
    else:
        lx -= int (round (min_shift1))
        ux -= int (round (max_shift1))
    if max_shift2 >= 0:
        ly -= int (round (max_shift2))
        uy -= int (round (min_shift2))
    else:
        ly -= int (round (min_shift2))
        uy -= int (round (max_shift2))

    lx += int (round (mindopp))
    ux += int (round (maxdopp))

    ccos.bindq (lx, ly, ux, uy, dq_info.field ("dq"),
                dq_array, info["x_offset"])

def flagOutOfBounds (phdr, hdr, dq_array, stim_param, info, switches,
                     brftab, geofile, minmax_shifts, minmax_doppler):
    """Flag regions that are outside all subarrays (done in-place).

    @param phdr: the primary header
    @type phdr: pyfits Header object
    @param hdr: the extension header
    @type hdr: pyfits Header object
    @param dq_array: data quality image array (modified in-place)
    @type dq_array: numpy array
    @param stim_param: a dictionary of lists, with keys
        i0, i1, x0, xslope, y0, yslope
    @type stim_param: dictionary
    @param info: keywords and values
    @type info: dictionary
    @param switches: calibration switches
    @type switches: dictionary
    @param brftab: name of baseline reference table (for active area)
    @type brftab: string
    @param minmax_shifts: the min and max offsets in the dispersion direction
        and the min and max offsets in the cross-dispersion direction during
        the exposure
    @type minmax_shifts: tuple
    @param minmax_doppler: minimum and maximum Doppler shifts (will be 0 if
        doppcorr is omit)
    @type minmax_doppler: tuple
    """

    if not phdr.has_key ("subarray"):
        return
    if not phdr["subarray"]:
        return

    nsubarrays = hdr.get ("nsubarry", 0)
    if nsubarrays < 1:
        return

    x_offset = info["x_offset"]
    detector = info["detector"]
    segment = info["segment"]

    if detector == "FUV":
        # Indices 0, 1, 2, 3 are for FUVA, while 4, 5, 6, 7 are for FUVB.
        indices = N.arange (4, dtype=N.int32)
        if phdr["segment"] == "FUVB":
            indices += 4
    else:
        indices = N.arange (nsubarrays, dtype=N.int32)

    temp = dq_array.copy()
    (ny, nx) = dq_array.shape

    # These are for shifting and smearing the out-of-bounds region into
    # the subarray due to the wavecal offset and Doppler shift and their
    # variation during the exposure.
    (min_shift1, max_shift1, min_shift2, max_shift2) = minmax_shifts
    (mindopp, maxdopp) = minmax_doppler

    dx = min_shift1
    dy = min_shift2
    dx -= maxdopp
    dx = int (round (dx))
    dy = int (round (dy))
    xwidth = int (round (max_shift1 - min_shift1 + maxdopp - mindopp))
    ywidth = int (round (max_shift2 - min_shift2))

    # get a list of subarray locations
    subarrays = []
    for i in indices:
        sub = {}
        sub_number = str (i)
        # these keywords are 0-indexed
        x0 = hdr["corner"+sub_number+"x"]
        y0 = hdr["corner"+sub_number+"y"]
        xsize = hdr["size"+sub_number+"x"]
        ysize = hdr["size"+sub_number+"y"]
        if xsize <= 0 or ysize <= 0:
            continue
        if detector == "FUV" and (ysize, xsize) == (FUV_Y, FUV_X):
            continue
        if detector == "NUV" and (ysize, xsize) == (NUV_Y, NUV_X):
            continue
        x1 = x0 + xsize - xwidth
        y1 = y0 + ysize - ywidth
        sub["x0"] = x0
        sub["y0"] = y0
        sub["x1"] = x1
        sub["y1"] = y1
        subarrays.append (sub)
    if not subarrays:
        # Create one full-size "subarray" in order to account for the NUV
        # image being larger than the detector and because of fpoffset.
        sub["x0"] = 0
        sub["y0"] = 0
        if detector == "FUV":
            sub["x1"] = FUV_X
            sub["y1"] = FUV_Y
        else:
            sub["x1"] = NUV_X
            sub["y1"] = NUV_Y
        subarrays.append (sub)

    # Initially flag the entire image as out of bounds, then remove the
    # flag (set it to zero) for each subarray.
    temp[:,:] = DQ_OUT_OF_BOUNDS
    (ny, nx) = dq_array.shape

    if switches["tempcorr"] == "PERFORM":
        # These are the parameters found by computeThermalParam.
        xintercept = stim_param["x0"]
        xslope = stim_param["xslope"]
        yintercept = stim_param["y0"]
        yslope = stim_param["yslope"]
        # check the length; we expect (for accum mode) only one element
        if len (xintercept) != 1:
            printWarning ("in flagOutOfBounds, more stim_param than expected")
        xintercept = xintercept[0]
        xslope = xslope[0]
        yintercept = yintercept[0]
        yslope = yslope[0]

        # subarrays is a list of dictionaries, each with keys:
        #     "x0", "x1", "y0", "y1"
        # x is the more rapidly varying axis (dispersion direction), and
        # y is the less rapidly varying axis.  The limits can be used as a
        # slice, i.e. x1 and y1 are one larger than the actual upper limits.
        new_subarrays = []
        for sub in subarrays:
            x0 = sub["x0"]
            x1 = sub["x1"]
            y0 = sub["y0"]
            y1 = sub["y1"]
            # apply the correction for thermal distortion
            sub["x0"] = xintercept + x0 * xslope
            sub["y0"] = yintercept + y0 * yslope
            sub["x1"] = xintercept + (x1 - 1.) * xslope + 1.
            sub["y1"] = yintercept + (y1 - 1.) * yslope + 1.
            new_subarrays.append (sub)
        del subarrays
        subarrays = new_subarrays

    # Add shifts, apply geometric correction to the subarray for the
    # source spectrum, and set flags to zero in temp within subarrays.
    (b_low, b_high, b_left, b_right) = activeArea (segment, brftab)
    nfound = 0
    save_sub = None
    for sub in subarrays:
        x0 = sub["x0"]
        x1 = sub["x1"]
        y0 = sub["y0"]
        y1 = sub["y1"]
        # the subarrays for the stims are outside the active area
        if y1 < b_low or y0 > b_high:
            clearSubarray (temp, x0, x1, y0, y1, dx, dy, x_offset)
            continue
        nfound += 1
        # These are arrays of pixel coordinates just inside the borders
        # of the subarray.
        x_lower = N.arange (x0, x1, dtype=N.float32)
        x_upper = N.arange (x0, x1, dtype=N.float32)
        y_left  = N.arange (y0, y1, dtype=N.float32)
        y_right = N.arange (y0, y1, dtype=N.float32)
        y_lower = y0 + 0. * x_lower
        y_upper = (y1 - 1.) + 0. * x_upper
        x_left  = x0 + 0. * y_left
        x_right = (x1 - 1.) + 0. * y_right
        # These are independent variable arrays for interpolation.
        x_lower_uniform = N.arange (nx, dtype=N.float32)
        x_upper_uniform = N.arange (nx, dtype=N.float32)
        y_left_uniform  = N.arange (ny, dtype=N.float32)
        y_right_uniform = N.arange (ny, dtype=N.float32)
        # These will be the arrays of interpolated edge coordinates.
        y_lower_interp = N.arange (nx, dtype=N.float32)
        y_upper_interp = N.arange (nx, dtype=N.float32)
        x_left_interp  = N.arange (ny, dtype=N.float32)
        x_right_interp = N.arange (ny, dtype=N.float32)
        save_sub = (x0, x1, y0, y1)             # in case geocorr is omit
    if nfound == 0:
        printWarning (
        "in flagOutOfBounds, there should be at least one full-size 'subarray'")
    if nfound > 1:
        printWarning ("in flagOutOfBounds, more subarrays than expected")
    if switches["geocorr"] == "PERFORM":
        interp_flag = (switches["igeocorr"] == "PERFORM")
        (x_data, origin_x, xbin, y_data, origin_y, ybin) = \
                        getGeoData (geofile, segment)
        # Undistort x_lower, y_lower, etc., in-place.
        ccos.geocorrection (x_lower, y_lower, x_data, y_data, interp_flag,
                            origin_x, origin_y, xbin, ybin)
        ccos.geocorrection (x_upper, y_upper, x_data, y_data, interp_flag,
                            origin_x, origin_y, xbin, ybin)
        ccos.geocorrection (x_left, y_left, x_data, y_data, interp_flag,
                            origin_x, origin_y, xbin, ybin)
        ccos.geocorrection (x_right, y_right, x_data, y_data, interp_flag,
                            origin_x, origin_y, xbin, ybin)
        del (x_data, y_data)
        # Interpolate to uniform spacing (pixel spacing).
        ccos.interp1d (x_lower, y_lower, x_lower_uniform, y_lower_interp)
        ccos.interp1d (x_upper, y_upper, x_upper_uniform, y_upper_interp)
        ccos.interp1d (y_left,  x_left,  y_left_uniform,  x_left_interp)
        ccos.interp1d (y_right, x_right, y_right_uniform, x_right_interp)
        # Apply offsets for zero point and wavecal shifts, replacing the
        # previous x_lower, y_lower, etc.  The independent variable arrays
        # will now be uniform, and the dependent variable arrays will have
        # been interpolated onto the uniform grid.
        (y_lower, y_upper) = applyOffsets (y_lower_interp, y_upper_interp,
                                           ny, dy)
        (x_left, x_right)  = applyOffsets (x_left_interp, x_right_interp,
                                           nx, dx, x_offset)

        ccos.clear_rows (temp, y_lower, y_upper, x_left, x_right)
    elif save_sub is not None:
        (x0, x1, y0, y1) = save_sub
        clearSubarray (temp, x0, x1, y0, y1, dx, dy, x_offset)

    dq_array[:,:] = N.bitwise_or (dq_array, temp)

def applyOffsets (x_left, x_right, nx, dx, x_offset=0):

    x_left += x_offset
    x_right += x_offset
    x_left -= dx
    x_right -= dx
    x_left = N.where (x_left < 0., 0., x_left)
    x_right = N.where (x_right > nx-1., nx-1., x_right)

    return (x_left, x_right)

def clearSubarray (temp, x0, x1, y0, y1, dx, dy, x_offset):
    """Set the subarray to zero in temp."""

    (ny, nx) = temp.shape
    x0 += x_offset
    x0 -= dx
    y0 -= dy
    x1 += x_offset
    x1 -= dx
    y1 -= dy
    x0 = max (x0, 0)
    y0 = max (y0, 0)
    x1 = min (x1, nx)
    y1 = min (y1, ny)
    temp[y0:y1,x0:x1] = DQ_OK

def flagOutsideActiveArea (dq_array, segment, brftab,
                           minmax_shifts, minmax_doppler):
    """Flag the region that is outside the active area.

    This is only relevant for FUV data.

    @param dq_array: 2-D data quality array, modified in-place
    @type dq_array: numpy array
    @param segment: segment name (FUVA or FUVB)
    @type segment: string
    @param brftab: name of baseline reference table
    @type brftab: string
    @param minmax_shifts: the min and max offsets in the dispersion direction
        and the min and max offsets in the cross-dispersion direction during
        the exposure
    @type minmax_shifts: tuple
    """

    if segment[0:3] != "FUV":
        return

    (b_low, b_high, b_left, b_right) = activeArea (segment, brftab)

    # These are for shifting and smearing the out-of-bounds region into
    # the active region due to the wavecal offset and Doppler shift and
    # their variation during the exposure.
    (min_shift1, max_shift1, min_shift2, max_shift2) = minmax_shifts
    (mindopp, maxdopp) = minmax_doppler

    b_left -= int (round (min_shift1))
    b_right -= int (round (max_shift1))
    b_low -= int (round (min_shift2))
    b_high -= int (round (max_shift2))

    b_left += int (round (maxdopp))
    b_right += int (round (mindopp))

    (ny, nx) = dq_array.shape

    if b_low >= 0:
        dq_array[0:b_low,:]    |= DQ_OUT_OF_BOUNDS
    if b_high < ny-1:
        dq_array[b_high+1:,:]  |= DQ_OUT_OF_BOUNDS
    if b_left >= 0:
        dq_array[:,0:b_left]   |= DQ_OUT_OF_BOUNDS
    if b_right < nx-1:
        dq_array[:,b_right+1:] |= DQ_OUT_OF_BOUNDS

def getGeoData (geofile, segment):
    """Open and read the geofile.

    @param geofile: name of geometric correction reference file
    @type geofile: string
    @param segment: FUVA or FUVB
    @type segment: string

    @return: the data from the geofile for X and Y, and the offsets;
        x_hdu.data:  array to correct distortion in X
        origin_x:  offset of x_hdu.data within detector coordinates
        xbin:  binning (int) in the X direction
        y_hdu.data:  array to correct distortion in Y
        origin_y:  offset of y_hdu.data within detector coordinates
        ybin:  binning (int) in the Y direction
    @rtype: tuple
    """

    fd = pyfits.open (geofile, mode="readonly", memmap=0)
    x_hdu = fd[(segment,1)]
    y_hdu = fd[(segment,2)]

    # The images in the geofile will typically be smaller than the full
    # detector.  These offsets give the location of geofile pixel [0,0]
    # on the detector.
    origin_x = x_hdu.header.get ("origin_x", 0)
    origin_y = x_hdu.header.get ("origin_y", 0)

    if origin_x != y_hdu.header.get ("origin_x", 0) or \
       origin_y != y_hdu.header.get ("origin_y", 0):
        raise RuntimeError, "Inconsistent ORIGIN_X or _Y keywords in GEOFILE"

    xbin = x_hdu.header.get ("xbin", 1)
    ybin = x_hdu.header.get ("ybin", 1)
    if xbin != y_hdu.header.get ("xbin", 1) or \
       ybin != y_hdu.header.get ("ybin", 1):
        raise RuntimeError, "Inconsistent XBIN or YBIN keywords in GEOFILE"

    # "touch" the data before closing the file.  Is this necessary?
    x_data = x_hdu.data
    y_data = y_hdu.data

    fd.close()

    return (x_data, origin_x, xbin, y_data, origin_y, ybin)

def tableHeaderToImage (thdr):
    """Rename table WCS keywords to image WCS keywords.

    The function returns a copy of the header with table-specific WCS
    keywords renamed to their image-style counterparts, to serve as an
    image header.

    argument:
    thdr          a FITS Header object for a table
    """

    hdr = thdr.copy()

    # These are the world coordinate system keywords in an events table
    # and their corresponding names for an image.  NOTE that this assumes
    # that the XCORR and YCORR columns are 2 and 3 (one indexed).
    tkey = ["TCTYP2", "TCRVL2", "TCRPX2", "TCDLT2", "TCUNI2", "TC2_2", "TC2_3",
            "TCTYP3", "TCRVL3", "TCRPX3", "TCDLT3", "TCUNI3", "TC3_2", "TC3_3"]
    ikey = ["CTYPE1", "CRVAL1", "CRPIX1", "CDELT1", "CUNIT1", "CD1_1", "CD1_2",
            "CTYPE2", "CRVAL2", "CRPIX2", "CDELT2", "CUNIT2", "CD2_1", "CD2_2"]
    # Rename events table WCS keywords to the corresponding image WCS keywords.
    for i in range (len (tkey)):
        if hdr.has_key (tkey[i]):
            if hdr.has_key (ikey[i]):
                printWarning ("Can't rename %s to %s" % (tkey[i], ikey[i]))
                printContinuation ("keyword already exists")
                del (hdr[tkey[i]])
            else:
                hdr.rename_key (tkey[i], ikey[i])

    return hdr

def imageHeaderToTable (imhdr):
    """Modify keywords to turn an image header into a table header.

    The function returns a copy of the header with image-specific world
    coordinate system keywords and BUNIT deleted.

    arguments:
    imhdr         a FITS Header object for an image
    """

    hdr = imhdr.copy()

    ikey = ["CTYPE1", "CRVAL1", "CRPIX1", "CDELT1", "CUNIT1", "CD1_1", "CD1_2",
            "CTYPE2", "CRVAL2", "CRPIX2", "CDELT2", "CUNIT2", "CD2_1", "CD2_2",
            "BUNIT"]
    for keyword in ikey:
        if hdr.has_key (keyword):
            del hdr[keyword]

    return hdr

def delCorrtagWCS (thdr):
    """Delete table WCS keywords.

    The function returns a copy of the header with table-specific WCS keywords
    deleted.  This is appropriate when creating an x1d table from a corrtag
    table.

    argument:
    thdr          a FITS Header object for a table
    """

    hdr = thdr.copy()

    # These are the world coordinate system keywords in an events table.
    # NOTE that this assumes that the XCORR and YCORR columns are 2 and 3
    # (one indexed).
    tkey = ["TCTYP2", "TCRVL2", "TCRPX2", "TCDLT2", "TCUNI2", "TC2_2", "TC2_3",
            "TCTYP3", "TCRVL3", "TCRPX3", "TCDLT3", "TCUNI3", "TC3_2", "TC3_3"]
    for keyword in tkey:
        if hdr.has_key (keyword):
            del hdr[keyword]

    return hdr

def updateFilename (phdr, filename):
    """Update the FILENAME keyword in a primary header.

    This routine will update (or add) the FILENAME keyword.  If filename
    includes a directory, that will not be included in the keyword value.

    arguments:
    phdr        primary header
    filename    may include directory
    """

    phdr.update ("filename", os.path.basename (filename))

def renameFile (infile, outfile):
    """Rename a FITS file, and update the FILENAME keyword.

    @param infile: current name of a FITS file
    @type infile: string
    @param outfile: new name for the file
    @type outfile: string
    """

    printMsg ("rename " + infile + " --> " + outfile, VERY_VERBOSE)

    os.rename (infile, outfile)

    fd = pyfits.open (outfile, mode="update")

    # If the output file name is a product name (ends with '0' before
    # the suffix), change the value of the extension keyword ASN_MTYP.
    if isProduct (outfile):
        asn_mtyp = fd[1].header.get ("asn_mtyp", "missing")
        asn_mtyp = modifyAsnMtyp (asn_mtyp)
        if asn_mtyp != "missing":
            fd[1].header["asn_mtyp"] = asn_mtyp
    updateFilename (fd[0].header, outfile)

    fd.close()

def copyFile (infile, outfile):
    """Copy a FITS file, and update the FILENAME keyword.

    @param infile: name of input FITS file
    @type infile: string
    @param outfile: name of output FITS file
    @type outfile: string
    """

    printMsg ("copy " + infile + " --> " + outfile, VERY_VERBOSE)

    shutil.copy (infile, outfile)

    fd = pyfits.open (outfile, mode="update")

    # If the output file name is a product name (ends with '0' before
    # the suffix), change the value of the extension keyword ASN_MTYP.
    if isProduct (outfile):
        asn_mtyp = fd[1].header.get ("asn_mtyp", "missing")
        asn_mtyp = modifyAsnMtyp (asn_mtyp)
        if asn_mtyp != "missing":
            fd[1].header["asn_mtyp"] = asn_mtyp
    updateFilename (fd[0].header, outfile)

    fd.close()

def isProduct (filename):
    """Return True if 'filename' is a "product" name.

    @param filename: name of an output file
    @type filename: string
    @return: True if the root part (before the suffix) of 'filename'
        ends in '0', implying that it is a product name
    @rtype: boolean
    """

    is_product = False          # may be changed below
    i = filename.rfind ("_")
    if i > 0 and filename[i:] == "_a.fits" or filename[i:] == "_b.fits":
        i = filename[0:i-1].rfind ("_")
    if i > 0 and filename[i-1] == '0':
        is_product = True

    return is_product

def modifyAsnMtyp (asn_mtyp):
    """Replace 'EXP' with 'PROD' in the ASN_MTYP keyword string.

    @param asn_mtyp: value of ASN_MTYP keyword from an input file
    @type asn_mtyp: string
    @return: modified asn_mtyp
    @rtype: string
    """

    if asn_mtyp.startswith ("EXP-") or asn_mtyp.startswith ("EXP_"):
        asn_mtyp = "PROD" + asn_mtyp[3:]

    return asn_mtyp

def doImageStat (input):
    """Compute statistics for an image, and update keywords in header.

    argument:
    input       name of FITS file; keywords in the file will be modified
                in-place
    """

    fd = pyfits.open (input, mode="update")

    if fd[1].data is None:
        fd.close()
        return
    phdr = fd[0].header
    xtractab = expandFileName (phdr.get ("xtractab", ""))
    detector = phdr.get ("detector", "")
    if detector == "FUV":
        fuv_segment = phdr.get ("segment", "")  # not used for NUV
    opt_elem = phdr.get ("opt_elem", "")
    cenwave = phdr.get ("cenwave", 0)
    aperture = getApertureKeyword (phdr, truncate=1)
    exptype = phdr.get ("exptype", "")
    nextend = len (fd) - 1      # number of extensions
    nimsets = nextend // 3      # number of image sets

    for k in range (nimsets):
        extver = k + 1          # extver is one indexed

        hdr = fd[("SCI",extver)].header
        sci = fd[("SCI",extver)].data
        err = fd[("ERR",extver)].data
        dq = fd[("DQ",extver)].data

        dispaxis = hdr.get ("dispaxis", 0)
        exptime = hdr.get ("exptime", 0.)
        sdqflags = hdr.get ("sdqflags", 3832)
        x_offset = hdr.get ("x_offset", 0)

        if exptype == "ACQ/IMAGE":
            dispaxis = 0

        if dispaxis > 0:
            axis = 2 - dispaxis         # 1 --> 1,  2 --> 0
            axis_length = fd[1].data.shape[axis]

        # This will be a list of dictionaries, one for FUV, three for NUV.
        stat_info = []

        if detector == "FUV":
            segment_list = [fuv_segment]            # just one
        elif dispaxis == 0:
            segment_list = ["NUV"]                  # target-acq image
        else:
            segment_list = ["NUVA", "NUVB", "NUVC"]

        for segment in segment_list:

            if dispaxis > 0:
                filter = {"segment": segment,
                          "opt_elem": opt_elem,
                          "cenwave": cenwave,
                          "aperture": aperture}

                xtract_info = getTable (xtractab, filter)
                if xtract_info is None:
                    continue

                slope = xtract_info.field ("slope")[0]
                b_spec = xtract_info.field ("b_spec")[0]
                extr_height = xtract_info.field ("height")[0]

                sci_band = N.zeros ((extr_height, axis_length),
                                       dtype=N.float32)
                ccos.extractband (sci, axis, slope, b_spec, x_offset,
                                  sci_band)

                if err is None:
                    err_band = None
                else:
                    err_band = N.zeros ((extr_height, axis_length),
                                       dtype=N.float32)
                    ccos.extractband (err, axis, slope, b_spec, x_offset,
                                      err_band)

                if dq is None:
                    dq_band = None
                else:
                    dq_band = N.zeros ((extr_height, axis_length),
                                          dtype=N.int16)
                    ccos.extractband (dq, axis, slope, b_spec, x_offset,
                                      dq_band)

                stat_info.append (computeStat (sci_band,
                              err_band, dq_band, sdqflags))

            else:
                # This is presumably a target-acquisition image.  Compute info
                # for the entire image.
                stat_info.append (computeStat (sci, err, dq, sdqflags))

        # Combine the three NUV stripes, or for FUV return the first element.
        stat_avg = combineStat (stat_info)

        sci_hdr = fd[("SCI",extver)].header
        sci_hdr.update ("ngoodpix", stat_avg["ngoodpix"])
        sci_hdr.update ("goodmean", exptime * stat_avg["sci_goodmean"])
        sci_hdr.update ("goodmax", exptime * stat_avg["sci_goodmax"])
        if err is not None:
            err_hdr = fd[("ERR",extver)].header
            err_hdr.update ("ngoodpix", stat_avg["ngoodpix"])
            err_hdr.update ("goodmean", exptime * stat_avg["err_goodmean"])
            err_hdr.update ("goodmax", exptime * stat_avg["err_goodmax"])

    fd.close()

def doSpecStat (input):
    """Compute statistics for a table, and update keywords in header.

    The NET column will be read, and statistics computed for all rows.

    argument:
    input       name of FITS file; keywords in the file will be modified
                in-place
    """

    fd = pyfits.open (input, mode="update")
    try:
        sci_extn = fd["SCI"]
    except KeyError:
        doTagFlashStat (fd)                     # extname is "LAMPFLASH"
        fd.close()
        return

    if sci_extn.data is None:
        fd.close()
        return
    sdqflags = sci_extn.header["sdqflags"]
    outdata = sci_extn.data
    nrows = outdata.shape[0]
    if nrows < 1:
        fd.close()
        return
    exptime_col = outdata.field ("EXPTIME")
    net = outdata.field ("NET")
    error = outdata.field ("ERROR")
    dq = outdata.field ("DQ")

    # This will be a list of dictionaries, one for each segment or stripe.
    # (statistics for the error array are computed but then ignored)
    stat_info = []
    sum_exptime = 0.
    for row in range (nrows):
        sum_exptime += exptime_col[row]
        onestat = computeStat (net[row], error[row], dq[row], sdqflags)
        stat_info.append (onestat)
    exptime = sum_exptime / nrows

    # Combine the segments or stripes.
    stat_avg = combineStat (stat_info)

    sci_extn.header.update ("ngoodpix", stat_avg["ngoodpix"])
    sci_extn.header.update ("goodmean", exptime * stat_avg["sci_goodmean"])
    sci_extn.header.update ("goodmax", exptime * stat_avg["sci_goodmax"])

    fd.close()

def doTagFlashStat (fd):
    """Compute statistics for an (already open) tagflash output file.

    The GROSS column will be read, and statistics computed for all rows.

    argument:
    fd          HDU list for the FITS file (opened by doSpecStat)
    """

    sci_extn = fd["LAMPFLASH"]
    if sci_extn.data is None:
        return

    outdata = sci_extn.data
    nrows = outdata.shape[0]
    if nrows < 1:
        return
    nelem = outdata.field ("NELEM")
    gross = outdata.field ("GROSS")

    sum_gross = 0.
    max_gross = 0.
    n = 0
    for row in range (nrows):
        max_gross = max (max_gross, N.maximum.reduce (gross[row]))
        sum_gross += N.sum (gross[row])
        n += nelem[row]

    sci_extn.header.update ("ngoodpix", n)
    sci_extn.header.update ("goodmean", sum_gross / float (n))
    sci_extn.header.update ("goodmax", max_gross)

def computeStat (sci_band, err_band=None, dq_band=None, sdqflags=3832):
    """Compute statistics.

    The function value is a dictionary with the info.  The keys are the
    keyword names, except that ones that have the same keyword but different
    values in the SCI and ERR extensions (goodmean, goodmax) have
    sci_ or err_ prefixes.

    arguments:
    sci_band       science data array for which statistics are needed
    err_band       error array (but may be None) associated with sci_band
    dq_band        data quality array (may be None) associated with sci_band
    sdqflags       "serious" data quality flags
    """

    # default values:
    stat_info = {"ngoodpix": 0, "sci_goodmax": 0., "sci_goodmean": 0.,
                                "err_goodmax": 0., "err_goodmean": 0.}

    # Don't quit if there are numpy exceptions.
    # xxx N.Error.setMode (all="warn", underflow="ignore")

    # Compute statistics for the sci array.  Note that mask is used
    # for both the sci and err arrays (if there is a dq_band).
    if dq_band is None:
        sci_good = N.ravel (sci_band)
    else:
        serious_dq = dq_band & sdqflags
        # mask = 1 where dq == 0
        mask = N.where (serious_dq == 0)
        sci_good = sci_band[mask]

    ngoodpix = len (sci_good)
    stat_info["ngoodpix"] = ngoodpix
    if ngoodpix > 0:
        stat_info["sci_goodmax"] = N.maximum.reduce (sci_good)
        stat_info["sci_goodmean"] = N.sum (sci_good) / ngoodpix
    del sci_good

    # Compute statistics for the err array.
    if err_band is not None:
        if dq_band is None:
            err_good = N.ravel (err_band)
        else:
            err_good = err_band[mask]
        if ngoodpix > 0:
            stat_info["err_goodmax"] = N.maximum.reduce (err_good)
            stat_info["err_goodmean"] = \
                      N.sum (err_good) / ngoodpix

    return stat_info

def combineStat (stat_info):
    """Combine statistical info for the segments or stripes.

    The input is a list of dictionaries.  The output is one dictionary
    with the same keys and with values that are the averages of the input.

    argument:
    stat_info      list of dictionaries, one for each segment (or stripe)
    """

    if len (stat_info) == 1:
        return stat_info[0]

    # Initialize these variables.
    sum_n = 0
    sci_max = 0.
    sci_sum = 0.
    err_max = 0.
    err_sum = 0.

    for stat in stat_info:
        n = stat["ngoodpix"]
        if n > 0:
            sum_n += n
            sci_max = max (sci_max, stat["sci_goodmax"])
            sci_sum += (n * stat["sci_goodmean"])
            if stat.has_key ("err_goodmax"):
                err_max = max (err_max, stat["err_goodmax"])
                err_sum += (n * stat["err_goodmean"])

    if sum_n > 0:
        sci_sum /= float (sum_n)
        err_sum /= float (sum_n)

    return {"ngoodpix": sum_n,
            "sci_goodmax": sci_max, "sci_goodmean": sci_sum,
            "err_goodmax": err_max, "err_goodmean": err_sum}

def overrideKeywords (phdr, hdr, info, switches, reffiles):
    """Override the calibration switch and reference file keywords.

    The calibration switch and reference file keywords and a few other
    specific keywords will be overridden.  The x_offset keyword will be set.

    arguments:
    phdr          primary header from input
    hdr           extension header from input
    info          dictionary of keywords and values
    switches      dictionary of calibration switches
    reffiles      dictionary of reference file names
    """

    for key in switches.keys():
        if phdr.has_key (key):
            if key == "statflag":
                if switches["statflag"] == "PERFORM":
                    phdr["statflag"] = True
                else:
                    phdr["statflag"] = False
            else:
                phdr[key] = switches[key]

    for key in reffiles.keys():
        # Skip the _hdr keys (they're redundant), and skip any keyword
        # that isn't already in the header.
        if key.find ("_hdr") < 0 and phdr.has_key (key):
            phdr[key] = reffiles[key+"_hdr"]

    for key in ["cal_ver", "opt_elem", "cenwave", "fpoffset", \
                "obstype", "exptype"]:
        if phdr.has_key (key):
            phdr[key] = info[key]

    if hdr.has_key ("dispaxis"):
        hdr["dispaxis"] = info["dispaxis"]

    hdr.update ("x_offset", info["x_offset"])

def updatePulseHeightKeywords (hdr, segment, low, high):
    """Update the screening limit keywords for pulse height.

    This is only used for FUV data, since NUV doesn't have pulse height info.

    arguments:
    hdr            header with keywords to be modified
    segment        FUVA or FUVB (last character used to construct keyword names)
    low, high      values for PHALOWR[AB] and PHAUPPR[AB] respectively
    """

    key_low  = "PHALOWR" + segment[-1]
    hdr.update (key_low, low)
    key_high = "PHAUPPR" + segment[-1]
    hdr.update (key_high, high)

def getSwitch (phdr, keyword):
    """Get the value of a calibration switch from a primary header.

    The value will be converted to upper case.  If the keyword is STATFLAG,
    the header value T or F will be converted to PERFORM or OMIT
    respectively.

    arguments:
    phdr           primary header
    keyword        name of keyword to get from header
    """

    if phdr.has_key (keyword):
        switch = phdr[keyword]
        if keyword.upper() == "STATFLAG":
            if switch:
                switch = "PERFORM"
            else:
                switch = "OMIT"
        switch = switch.upper()
    else:
        switch = NOT_APPLICABLE

    return switch

def setVerbosity (verbosity_level):
    """Copy verbosity to a variable that is global for this file.

    argument:
    verbosity_level   an integer value indicating the level of verbosity
    """

    global verbosity
    verbosity = verbosity_level

def checkVerbosity (level):
    """Return true if verbosity is at least as great as level.

    >>> setVerbosity (VERBOSE)
    >>> print checkVerbosity (QUIET)
    1
    >>> print checkVerbosity (VERBOSE)
    1
    >>> print checkVerbosity (VERY_VERBOSE)
    0
    """

    return (verbosity >= level)

def openTrailer (filename):
    """Open the trailer file for 'filename' in append mode.

    @param filename: name of an input (science or wavecal) file
    @type filename: string
    """

    global fd_trl

    closeTrailer()

    fd_trl = open (filename, 'a')

def writeVersionToTrailer():
    """Write the calcos version string to the trailer file."""

    if fd_trl is not None:
        fd_trl.write ("CALCOS version " + CALCOS_VERSION + "\n")
        fd_trl.flush()

def closeTrailer():
    """Close the trailer file if it is open."""

    global fd_trl

    if fd_trl is not None and not fd_trl.closed:
        fd_trl.close()
    fd_trl = None

def printMsg (message, level=QUIET):
    """Print 'message' if verbosity is at least as great as 'level'.

    >>> setVerbosity (VERBOSE)
    >>> printMsg ("quiet", QUIET)
    quiet
    >>> printMsg ("verbose", VERBOSE)
    verbose
    >>> printMsg ("very verbose", VERY_VERBOSE)
    """

    if verbosity >= level:
        print message
        sys.stdout.flush()
        if fd_trl is not None:
            fd_trl.write (message+"\n")
            fd_trl.flush()

def printIntro (str):
    """Print introductory message.

    argument:
    str            string to be printed
    """

    printMsg ("", VERBOSE)
    printMsg (str + " -- " + returnTime(), VERBOSE)

def printFilenames (names, stimfile=None, livetimefile=None):
    """Print input and output filenames.

    arguments:
    names         a list of (label, filename) tuples
    stimfile      name of output text file for stim positions (or None)
    livetimefile  name of output text file for livetime factors (or None)

    >>> setVerbosity (VERBOSE)
    >>> names = [("Input", "abc_raw.fits"), ("Output", "abc_flt.fits")]
    >>> printFilenames (names)
    Input     abc_raw.fits
    Output    abc_flt.fits
    >>> printFilenames (names, stimfile="stim.txt", livetimefile="live.txt")
    Input     abc_raw.fits
    Output    abc_flt.fits
    stim locations log file   stim.txt
    livetime factors log file live.txt
    """

    for (label, filename) in names:
        printMsg ("%-10s%s" % (label, filename), VERBOSE)

    if stimfile is not None:
        printMsg ("stim locations log file   " + stimfile, VERBOSE)
    if livetimefile is not None:
        printMsg ("livetime factors log file " + livetimefile, VERBOSE)

def printMode (info):
    """Print info about the observation mode.

    argument:
    info          dictionary of header keywords and values
    """

    if info["detector"] == "FUV":
        printMsg ("DETECTOR  FUV, segment " + info["segment"][-1], VERBOSE)
    else:
        printMsg ("DETECTOR  NUV", VERBOSE)
    printMsg ("EXPTYPE   " + info["exptype"], VERBOSE)
    if info["obstype"] == "SPECTROSCOPIC":
        printMsg ("OPT_ELEM  " + info["opt_elem"] + \
              ", CENWAVE " + str (info["cenwave"]), VERBOSE)
    else:
        printMsg ("OPT_ELEM  " + info["opt_elem"], VERBOSE)
    printMsg ("APERTURE  " + info["aperture"], VERBOSE)

    printMsg ("", VERBOSE)

def printSwitch (keyword, switches):
    """Print calibration switch name and value.

    arguments:
    keyword       keyword name of calibration switch (e.g. "flatcorr")
    switches      dictionary of calibration switches

    >>> setVerbosity (VERBOSE)
    >>> switches = {"statflag": "PERFORM", "flatcorr": "PERFORM", "geocorr": "COMPLETE", "randcorr": "SKIPPED"}
    >>> printSwitch ("statflag", switches)
    STATFLAG  T
    >>> printSwitch ("flatcorr", switches)
    FLATCORR  PERFORM
    >>> printSwitch ("geocorr", switches)
    GEOCORR   OMIT (already complete)
    >>> printSwitch ("randcorr", switches)
    RANDCORR  OMIT (skipped)
    """

    key_upper = keyword.upper()
    value = switches[keyword.lower()]
    if key_upper == "STATFLAG":
        if value == "PERFORM":
            message = "STATFLAG  T"
        else:
            message = "STATFLAG  F"
    else:
        if value == "COMPLETE":
            message = "%-9s OMIT (already complete)" % key_upper
        elif value == "SKIPPED":
            message = "%-9s OMIT (skipped)" % key_upper
        else:
            message = "%-9s %s" % (key_upper, value)
    printMsg (message, VERBOSE)

def printRef (keyword, reffiles):
    """Print reference file keyword and file name.

    arguments:
    keyword       keyword name for reference file name (e.g. "flatfile")
    reffiles      dictionary of reference file names

    >>> setVerbosity (VERBOSE)
    >>> reffiles = {"flatfile": "abc_flat.fits", "flatfile_hdr": "lref$abc_flat.fits"}
    >>> printRef ("flatfile", reffiles)
    FLATFILE= lref$abc_flat.fits
    """

    key_upper = keyword.upper()
    key_lower = keyword.lower()
    printMsg ("%-8s= %s" % (key_upper, reffiles[key_lower+"_hdr"]), VERBOSE)

def printWarning (message, level=QUIET):
    """Print a warning message."""

    printMsg ("Warning:  " + message, level)

def printError (message):
    """Print an error message."""

    printMsg ("ERROR:  " + message, level=QUIET)

def printContinuation (message, level=QUIET):
    """Print a continuation line of a warning or error message."""

    printMsg ("    " + message, level)

def returnTime():
    """Return the current date and time, formatted into a string."""

    return time.strftime ("%d-%b-%Y %H:%M:%S %Z", time.localtime (time.time()))

def getPedigree (switch, refkey, filename, level=VERBOSE):
    """Return the value of the PEDIGREE keyword.

    @param switch: keyword name for calibration switch
    @type switch: string
    @param refkey: keyword name for the reference file
    @type refkey: string
    @param filename: name of the reference file
    @type filename: string
    @param level: QUIET, VERBOSE, or VERY_VERBOSE
    @type level: integer

    @return: the value of the PEDIGREE keyword, or "OK" if not found
    @rtype: string
    """

    if filename == "N/A":
        return "OK"

    fd = pyfits.open (filename, mode="readonly")
    pedigree = fd[0].header.get ("pedigree", "OK")
    fd.close()
    if pedigree == "DUMMY":
        printWarning ("%s %s is a dummy file" % (refkey.upper(), filename),
                      level=VERBOSE)
        printContinuation ("so %s will not be done." %
                           switch.upper(), level=VERBOSE)

    return pedigree

def getApertureKeyword (hdr, truncate=1):
    """Get the value of the APERTURE keyword.

    arguments:
    hdr           pyfits Header object
    truncate      if true, strip "-FUV" or "-NUV" from keyword value
    """

    aperture = hdr.get ("aperture", NOT_APPLICABLE)
    if aperture == "RelMvReq":
        aperture = "PSA"
    elif truncate and aperture != NOT_APPLICABLE:
        aperture = aperture[0:3]

    return aperture

def expandFileName (filename):
    """Expand environment variable in a file name.

    If the input file name begins with either a Unix-style or IRAF-style
    environment variable (e.g. $lref/name_dqi.fits or lref$name_dqi.fits
    respectively), this routine expands the variable and returns a complete
    path name for the file.

    argument:
    filename      a file name, possibly including an environment variable
    """

    n = filename.find ("$")
    if n == 0:
        if filename != NOT_APPLICABLE:
            # Unix-style file name.
            filename = os.path.expandvars (filename)
    elif n > 0:
        # IRAF-style file name.
        temp = "$" + filename[0:n] + os.sep + filename[n+1:]
        filename = os.path.expandvars (temp)
        # If filename contains "//", delete one of them.
        double_sep = os.sep + os.sep
        i = filename.find (double_sep)
        if i != -1:
            filename = filename[:i+1] + filename[i+2:]

    return filename

def findRefFile (ref, missing, wrong_filetype, bad_version):
    """Check for the existence of a reference file.

    arguments:
      (missing, wrong_filetype and bad_version are dictionaries, with the
       reference file keyword as key.)
    ref             a dictionary with the following keys:
                      keyword (e.g. "FLATFILE")
                      filename (name of file)
                      calcos_ver (calcos version number)
                      min_ver (minimum acceptable version number)
                      filetype (e.g. "FLAT FIELD REFERENCE IMAGE")
    missing         messages about missing reference files
    wrong_filetype  messages about wrong FILETYPE keyword in reference files
    bad_version     messages about inconsistent version strings

    If the reference file does not exist, its name is added to the 'missing'
    dictionary.  If the file does exist, open the file and compare
    'filetype' with the value of the FILETYPE keyword in the primary header.
    If they're not the same (unless FILETYPE is "ANY"), then an entry is
    added to the 'wrong_filetype' dictionary.  The VCALCOS keyword is also
    gotten from the primary header (with a default value of "1.0").  If the
    version of the reference file is not consistent with calcos, the
    reference file name and error message will be added to the 'bad_version'
    dictionary.
    """

    keyword    = ref["keyword"]
    filename   = ref["filename"]
    calcos_ver = ref["calcos_ver"]
    min_ver    = ref["min_ver"]
    filetype   = ref["filetype"]

    if os.access (filename, os.R_OK):

        fd = pyfits.open (filename, mode="readonly")
        phdr = fd[0].header

        phdr_filetype = phdr.get ("FILETYPE", "ANY")
        if phdr_filetype != "ANY" and phdr_filetype != filetype:
            wrong_filetype[keyword] = (filename, filetype)

        if min_ver != "ANY":
            phdr_ver = phdr.get ("VCALCOS", "1.0")
            if type (phdr_ver) is not types.StringType:
                phdr_ver = str (phdr_ver)
            compare = cmpVersion (min_ver, phdr_ver, calcos_ver)
            if compare < 0:
                bad_version[keyword] = (filename,
                "  the reference file must be at least version " + min_ver)
            elif compare > 0:
                bad_version[keyword] = (filename,
                "  to use this reference file you must have calcos version " + \
                 phdr_ver + " or later.")

        fd.close()

    else:

        missing[keyword] = filename

def cmpVersion (min_ver, phdr_ver, calcos_ver):
    """Compare version strings.

    arguments:
    min_ver      calcos requires the reference file to be at least this
                   version
    phdr_ver     version of the reference file, read from its primary header
    calcos_ver   version of calcos

    This function returns 0 if the 'phdr_ver' is compatible with
    'calcos_ver' and 'min_ver', i.e. that the following conditions are met:

        min_ver <= phdr_ver <= calcos_ver

    If min_ver > phdr_ver, this function returns -1.
    If phdr_ver > calcos_ver, this function returns +1.

    Each string is first separated into a list of substrings, splitting
    on ".", and comparisons are made on the substrings one at a time.
    A comparison between min_ver="1a" and phdr_ver="1.0a" will fail,
    for example, because the strings will be separated into parts before
    comparing, and "1a" > "1".

    >>> print cmpVersion ("1", "1", "1.1")
    0
    >>> print cmpVersion ("1", "1.1", "1")
    1
    >>> print cmpVersion ("1.1", "1", "1")
    -1
    >>> print cmpVersion ("1.1", "1.1", "1.2")
    0
    >>> print cmpVersion ("1.1", "1.2", "1.1")
    1
    >>> print cmpVersion ("1.2", "1.1", "1.1")
    -1
    >>> print cmpVersion ("1.0", "1", "1a")
    0
    >>> print cmpVersion ("1.0", "1.0a", "1")
    1
    >>> print cmpVersion ("1.0a", "1", "1")
    -1
    >>> print cmpVersion ("1.0a", "1.0a", "1b")
    0
    >>> print cmpVersion ("1a", "1.0a", "1b")
    -1
    """

    minv = min_ver.split ('.')
    phdrv = phdr_ver.split ('.')
    calv = calcos_ver.split ('.')

    length = min (len (minv), len (phdrv), len (calv))

    # These are initial values.  They'll be reset if either test passes
    # (because of an inequality in a part of the version string), in which
    # case tests on subsequent parts of the version strings will be omitted.
    passed_min_test = 0
    passed_calcos_test = 0

    for i in range (length):
        if not passed_min_test:
            cmp = cmpPart (minv[i], phdrv[i])
            if cmp < 0:
                passed_min_test = 1
            elif cmp > 0:
                return -1
        if not passed_calcos_test:
            cmp = cmpPart (phdrv[i], calv[i])
            if cmp < 0:
                passed_calcos_test = 1
            elif cmp > 0:
                return 1

    if passed_min_test or passed_calcos_test:
        return 0

    if len (minv) > len (phdrv):
        return -1
    if len (phdrv) > len (calv):
        return 1

    return 0

def cmpPart (s1, s2):
    """Compare two strings.

    s1 and s2 are "parts" of version strings, i.e. each is a simple integer,
    possibly with one or more appended letters.  The function value will be
    -1, 0, or +1, depending on whether s1 is less than, equal to, or greater
    than s2 respectively.  Comparison is done first on the numerical part,
    and any appended string is used to break a tie.

    >>> print cmpPart ("1", "01")
    0
    >>> print cmpPart ("14", "104")
    -1
    >>> print cmpPart ("9", "13a")
    -1
    >>> print cmpPart ("13", "13a")
    -1
    >>> print cmpPart ("13a", "14")
    -1
    >>> print cmpPart ("13a", "13b")
    -1
    """

    if s1 == s2:
        return 0

    nine = ord ('9')

    int1 = 0
    str1 = ""
    for i in range (len (s1)):
        ich = ord (s1[i])
        if ich > nine:
            if i > 0:
                int1 = int (s1[0:i])
            str1 = s1[i:]
            break
        int1 = int (s1[0:i+1])

    int2 = 0
    str2 = ""
    for i in range (len (s2)):
        ich = ord (s2[i])
        if ich > nine:
            if i > 0:
                int2 = int (s2[0:i])
            str2 = s2[i:]
            break
        int2 = int (s2[0:i+1])

    if int1 < int2:
        return -1
    elif int1 > int2:
        return 1
    else:
        # The numerical parts are identical; use the letter(s) to break the tie.
        if str1 == str2:
            return 0
        elif str1 == "":
            return -1                   # the first string is "smaller"
        elif str2 == "":
            return 1                    # the first string is "larger"
        else:
            length = min (len (str1), len (str2))
            for i in range (length):
                ich1 = ord (str1[i])
                ich2 = ord (str2[i])
                if ich1 < ich2:
                    return -1
                elif ich1 > ich2:
                    return 1
            if len (str1) < len (str2):
                return -1
            else:
                return 1


def _test():
    import doctest, cosutil
    return doctest.testmod (cosutil)

if __name__ == "__main__":
    _test()
