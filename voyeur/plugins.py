import sys
import os
import glob
import itertools
import abc

class IPlugin(object):
  """Root interface for plugins."""
  
  # It would be great to use abc.ABCMeta, but this will conflict with enthought.traits.api.HasTraits, so no dice
  #__metaclass__ = abc.ABCMeta


class PluginManager(object):
    """
    Simple plugin manager.
    
    Allows loading plugins at path, and retrieving implementations of each interface.
    
    Example usage
    =============
    
    From within distribution root:
    
    >>> from voyeur.plugins import PluginManager
    >>> from voyeur.plugins import IPlugin
    >>>
    >>> PluginManager.load_plugins('test/python/fixtures/')
    >>> PluginManager.plugins_for_interface(IPlugin)
    set([<class 'voyeur.plugins.IProtocol'>, <class 'voyeur.plugins.ExamplePlugin'>])
    
    """
    
    @classmethod
    def load_plugins(self, path):
        """Load plugins in folder at path"""
        
        if os.path.isdir(path):
            sys.path.append(path)
            for pluginPath in glob.glob(os.path.join(path,'*.py')):
                execfile(pluginPath, globals())
        else:
            execfile(path, globals())
        
        
    @classmethod
    def plugins_for_interface(self, interfaceClass):
        """Return the set of plugin classes that implement interfaceClass"""
        
        return self._find_subclasses(interfaceClass)
        
        
    @classmethod
    def _find_subclasses(self, cls):
        "Recursively build set of all subclasses of class"
        """docstring for _all_subclasses"""
        
        result = set(cls.__subclasses__())
        
        for k in cls.__subclasses__():
            result = result.union(self._find_subclasses(k))
        
        return result
    
