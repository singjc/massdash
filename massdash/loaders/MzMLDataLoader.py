"""
massdash/loaders/MzMLDataLoader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""

from os.path import basename, splitext
from typing import Dict, List, Union, Literal
import numpy as np
import pandas as pd

# Loaders
from .access.MzMLDataAccess import MzMLDataAccess
from .GenericSpectrumLoader import GenericSpectrumLoader
# Structs
from ..structs import TransitionGroup, FeatureMap, TargetedDIAConfig, FeatureMapCollection, TopTransitionGroupFeatureCollection, TransitionGroupCollection
# Utils
from ..util import LOGGER


class MzMLDataLoader(GenericSpectrumLoader):
    '''
    Class to load data from MzMLFiles using a .osw output file or .tsv report file
    
    Attributes:
        rsltsFile: (str) The path to the report file (DIANN-TSV or OSW)
        dataFiles: (str/List[str]) The path to the mzML file(s)
        libraryFile: (str) The path to the library file (.tsv or .pqp)
        
    '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs) 
        self.dataAccess = [MzMLDataAccess(f, 'ondisk', verbose=self.verbose) for f in self.dataFiles]
        self.has_im = np.all([d.has_im for d in self.dataAccess])
                   
    def loadTransitionGroups(self, pep_id: str, charge: int, config: TargetedDIAConfig) -> Dict[str, TransitionGroup]:
        '''
        Loads the transition group for a given peptide ID and charge across all files

        Args:
            pep_id (str): Peptide ID
            charge (int): Charge
            config (TargetedDIAConfig): Configuration object containing the extraction parameters
        Return:
            dict[str, TransitionGroup]: Dictionary of TransitionGroups, with keys as filenames
        '''
        out_feature_map = self.loadFeatureMaps(pep_id, charge, config)

        return TransitionGroupCollection({ run: data.to_chromatograms() for run, data in out_feature_map.items() })
    
    def loadTransitionGroupsDf(self, pep_id: str, charge: int, config: TargetedDIAConfig) -> Dict[str, pd.DataFrame]:
        '''
        Loads the transition group for a given peptide ID and charge across all files into a pandas DataFrame
        
        Args:
            pep_id (str): Peptide ID
            charge (int): Charge
            config (TargetedDIAConfig): Configuration object containing the extraction parameters
        
        Return:
            dict[str, pd.DataFrame]: Dictionary of TransitionGroups, with keys as filenames
        '''
        out_feature_map = self.loadFeatureMaps(pep_id, charge, config)

        # for each run, groupby intensity and rt to get chromatogram
        out_transitions = { run:df.feature_df[['Annotation', 'int', 'rt']].groupby(['Annotation', 'rt']).sum().reset_index() for run, df in out_feature_map.items() }

        out_df =  pd.concat(out_transitions).reset_index().drop(columns='level_1').rename(columns=dict(level_0='run'))
        
        # Drop duplicate columns
        out_df = out_df.loc[:,~out_df.columns.duplicated()]
        return out_df

    def loadFeatureMaps(self, pep_id: str, charge: int, config=TargetedDIAConfig) -> FeatureMapCollection:
        '''
        Loads a dictionary of FeatureMaps (where the keys are the filenames) from the results file

        Args:
            pep_id (str): Peptide ID
            charge (int): Charge
        Returns:
            FeatureMapCollection: FeatureMapCollection containing FeatureMap objects for each file
        '''
        out = FeatureMapCollection()
        # use the first results file to get the feature location
        top_features = [ self.rsltsAccess[0].getTopTransitionGroupFeature(basename(splitext(d.filename)[0]), pep_id, charge) for d in self.dataAccess]
        self.libraryAccess.populateTransitionGroupFeatures(top_features)
        for d, t in zip(self.dataAccess, top_features):
            if t is None:
                LOGGER.debug(f"No feature found for {pep_id} {charge} in {d.runName}")
                out[d.runName] =  FeatureMap()
            else:
                out[d.runName] = d.reduce_spectra(t, config)
        return out