#!/usr/bin/env python

from setuptools import setup

setup(name='voyeur',
      version='1.2',
      description='Framework for Behavioral Trial-Based Protocols and Data Acquisition/Display',
      author='Rinberg lab, Admir Resulaj, Physion Consulting',
      author_email='Admir.Resulaj@nyumc.org',
      url='None',
      packages=['voyeur'],
      package_dir = {'': 'src'},
      install_requires = [
        'numpy',
        'DateUtils',
        'numexpr',
        'cython',
        'elementtree',
        'configobj',
        'pyserial'],
        #'TraitsBackendQT', # [nonets]
        #'Traits', # [nonets]
        #'TraitsGUI', # [nonets]
        #'enable',
        #'chaco'],
      license = "BSD", # But note a dependency on GPL PyQt for now
     )