'''
Created on Aug 22, 2011

@author: Admir Resulaj

Defines the RangeSelectionsOverlay class which is an extension of the chaco RangeSelectionOverlay class.
'''

# Major library imports
from numpy import arange, array, nonzero

# Enthought library imports
from chaco.api import arg_find_runs
from chaco.tools.api import RangeSelectionOverlay


class RangeSelectionsOverlay(RangeSelectionOverlay):
    """ Highlights the selected regions on a component.
    
    Looks at a given metadata field of self.component for regions to draw as 
    selected. Re-implements the __get_selection_screencoords() method for a faster,
    more efficient regions selection.
    """
    
    #------------------------------------------------------------------------
    # Private methods
    #------------------------------------------------------------------------
    
    def _get_selection_screencoords(self):
        """ Returns a tuple of (x1, x2) screen space coordinates of the start
        and end selection points.  
        
        If there is no current selection, then returns None.
        """
        ds = getattr(self.plot, self.axis)
        selection = ds.metadata[self.metadata_name]
        
        if selection is None or len(selection) == 1:
            return []
        # if not an even number of points, trim the last point
        elif len(selection)%2 != 0:
            del selection[-1]
        
        # "selections" metadata is a tuple of selection pairs
        if self.metadata_name == "selections":
            coords = []
            for index in range(len(selection)/2):
                interval = (selection[index*2],selection[index*2+1])
                coords.append(self.mapper.map_screen(array(interval)))
            return coords
            
        else:
            selection_points = len(selection)
            coords = []
            # treat the metadata as a mask on dataspace
            if len(ds._data) == selection_points:
                selected = nonzero(selection)[0]
                runs = arg_find_runs(selected)                
                for run in runs:
                    start = ds._data[selected[run[0]]]
                    end = ds._data[selected[run[1]-1]]
                    coords.append(self.mapper.map_screen(array((start, end))))
                
            # selection is tuples of selected regions in dataspace
            else:
                for index in range(len(selection)/2):
                    interval = (selection[index*2],selection[index*2+1])
                    coords.append(self.mapper.map_screen(array(interval)))
            return coords

# EOF
