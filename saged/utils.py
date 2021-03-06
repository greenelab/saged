""" A file full of useful functions """

import functools
import json
import pickle
from pathlib import Path
import random
from typing import Any, Dict, Set, Text, Union, List

import neptune
import numpy as np
import pandas as pd
import torch
import yaml
from rpy2.robjects import pandas2ri
from rpy2.robjects.packages import importr
from sklearn.metrics import accuracy_score


BLOOD_KEYS = ['blood',
              'blood (buffy coat)',
              'blood cells',
              'blood monocytes',
              'blood sample',
              'cells from whole blood',
              'fresh venous blood anticoagulated with 50 g/ml thrombin-inhibitor lepirudin',
              'healthy human blood',
              'host peripheral blood',
              'leukemic peripheral blood',
              'monocytes isolated from pbmc',
              'normal peripheral blood cells',
              'pbmc',
              'pbmcs',
              'peripheral blood',
              'peripheral blood (pb)',
              'peripheral blood mononuclear cell',
              'peripheral blood mononuclear cell (pbmc)',
              'peripheral blood mononuclear cells',
              'peripheral blood mononuclear cells (pbmc)',
              'peripheral blood mononuclear cells (pbmcs)',
              'peripheral blood mononuclear cells (pbmcs) from healthy donors',
              'peripheral maternal blood',
              'peripheral whole blood',
              'periphral blood',
              'pheripheral blood',
              'whole blood',
              'whole blood (wb)',
              'whole blood, maternal peripheral',
              'whole venous blood'
              ]


def parse_map_file(map_file_path: str) -> Dict[str, str]:
    '''Create a sample: label mapping from the pickled file output by label_samples.py

    Arguments
    ---------
    map_file_path: The path to a pickled file created by label_samples.py

    Returns
    -------
    sample_to_label: A string to string dict mapping sample ids to their corresponding label string
        E.g. {'GSM297791': 'sepsis'}
    '''
    sample_to_label = {}
    label_to_sample = None
    with open(map_file_path, 'rb') as map_file:
        label_to_sample, _ = pickle.load(map_file)

    for label in label_to_sample:
        for sample in label_to_sample[label]:
            sample_to_label[sample] = label

    return sample_to_label


def get_tissue(sample_metadata: Dict, sample: Text) -> Union[Text, None]:
    ''' Extract the tissue type for the given sample from the metadata

    Arguments
    ---------
    sample_metadata: A dictionary containing metadata about all samples in the dataset
    sample: The sample id

    Returns
    -------
    tissue: The tissue name, if present. Otherwise returns None
    '''
    try:
        ch1 = sample_metadata[sample]['refinebio_annotations'][0]['characteristics_ch1']
        for characteristic in ch1:
            if 'tissue:' in characteristic:
                tissue = characteristic.split(':')[1]
                tissue = tissue.strip().lower()
                return tissue
    # Catch exceptions caused by a field not being present
    except KeyError:
        return None

    # 'refinebio_annotations' is usually a length 1 list containing a dictionary.
    # Sometimes it's a length 0 list indicating there aren't annotations
    except IndexError:
        return None
    return None


def get_blood_sample_ids(metadata: Dict, sample_to_label: Dict[str, str]) -> Set[str]:
    """ Retrieve the sample identifiers for all samples in the datset that are from blood

    Arguments
    ---------
    metadata: A dictionary containing metadata about the dataset. Usually found in a file called
        aggregated_metadata.json
    sample_to_label: A mapping between sample identifiers and their disease label

    Returns
    -------
    sample_ids: The identifiers for all blood samples
    """
    sample_metadata = metadata['samples']

    # Find labeled and unlabeled blood samples
    labeled_samples = set(sample_to_label.keys())

    unlabeled_samples = set()
    for sample in sample_metadata:
        tissue = get_tissue(sample_metadata, sample)
        if tissue in BLOOD_KEYS and sample not in labeled_samples:
            unlabeled_samples.add(sample)

    sample_ids = labeled_samples.union(unlabeled_samples)

    return sample_ids


def run_combat(expression_values: np.array, batches: List[str]) -> np.array:
    """ Use ComBat to correct for batch effects

    Arguments
    ---------
    expression_values: A genes x samples matrix of expression values to be corrected
    batches: The batch e.g. platform, study, or experiment that each sample came from, in order

    Returns
    -------
    corrected_expression: A genes x samples matrix of batch corrected expression
    """
    sva = importr('sva')

    pandas2ri.activate()

    corrected_expression = sva.ComBat(expression_values, batches)

    return corrected_expression


def run_limma(expression_values: np.array,
              batches: List[str],
              second_batch: List[str] = None) -> np.array:
    """ Use limma to correct for batch effects

    Arguments
    ---------
    expression_values: A genes x samples matrix of expression values to be corrected
    batches: The batch e.g. platform, study, or experiment that each sample came from, in order
    second_batch: Another list of batch information to account for

    Returns
    -------
    corrected_expression: A genes x samples matrix of batch corrected expression
    """
    limma = importr('limma')

    pandas2ri.activate()

    if second_batch is None:
        return limma.removeBatchEffect(expression_values, batches)
    else:
        return limma.removeBatchEffect(expression_values, batches, second_batch)


def parse_label_file(label_file_path: Union[str, Path]) -> Dict[str, str]:
    """
    Create a sample to label mapping from the pickled file output by label_samples.py

    Arguments
    ---------
    map_file_path: The path to a pickled file created by label_samples.py

    Returns
    -------
    sample_to_label: A string to string dict mapping sample ids to their
        corresponding label string. E.g. {'GSM297791': 'sepsis'}
    """
    sample_to_label = {}
    label_to_sample = None
    with open(label_file_path, 'rb') as map_file:
        label_to_sample, _ = pickle.load(map_file)

    for label in label_to_sample:
        for sample in label_to_sample[label]:
            assert sample not in sample_to_label
            sample_to_label[sample] = label

    return sample_to_label


def parse_metadata_file(metadata_path: Union[str, Path]) -> dict:
    """
    Parse a json file containing metadata about a compendium's samples

    Arguments
    ---------
    metadata_path: The file containing metadata for all samples in the compendium

    Returns
    -------
    metadata: The json object stored at metadata_path
    """
    with open(metadata_path) as metadata_file:
        metadata = json.load(metadata_file)
        return metadata


@functools.lru_cache()
def load_compendium_file(compendium_path: Union[str, Path]) -> pd.DataFrame:
    """
    Load refine.bio compendium data from a tsv file

    Arguments
    ---------
    compendium_path: The path to the file containing the compendium of gene expression data

    Returns
    -------
    expression_df: A dataframe where the rows are genes anbd the columns are samples
    """
    # Assume the expression is a pickle file. If not, try opening it as a tsv
    try:
        expression_df = pd.read_pickle(compendium_path)
    except pickle.UnpicklingError:
        expression_df = pd.read_csv(compendium_path, sep='\t', index_col=0)

    return expression_df


def map_sample_to_study(metadata_json: dict, sample_ids: List[str]) -> Dict[str, str]:
    """
    Map each sample id to the study that generated it

    Arguments
    ---------
    metadata_json: The metadata for the whole compendium. This metadata is structured by the
        refine.bio pipeline, and will typically be found in a file called aggregated_metadata.json
    sample_ids:
        The accessions for each sample

    Returns
    -------
    sample_to_study:
        The mapping from sample accessions to the study they are a member of
    """
    experiments = metadata_json['experiments']
    id_set = set(sample_ids)

    sample_to_study = {}
    for study in experiments:
        for accession in experiments[study]['sample_accession_codes']:
            if accession in id_set:
                sample_to_study[accession] = study

    return sample_to_study


def get_samples_in_studies(samples: List[str],
                           studies: Set[str],
                           sample_to_study: Dict[str, str]) -> List[str]:
    """
    Find which samples from the list were generated by the given studies

    Arguments
    ---------
    samples: The accessions of all samples
    studies: The studies of interest that generated a subset of samples in the list
    sample_to_study: A mapping between each sample and the study that generated it

    Returns
    -------
    subset_samples: The samples that were generated by a study in `studies`
    """
    subset_samples = [sample for sample in samples if sample_to_study[sample] in studies]
    return subset_samples


def sigmoid_to_predictions(model_output: np.ndarray) -> torch.Tensor:
    """
    Convert the sigmoid output of a model to integer labels

    Arguments
    ---------
    predictions: The labels the model predicted

    Returns
    -------
    The integer labels predicted by the model
    """
    return torch.argmax(model_output, dim=-1)


def count_correct(outputs: torch.Tensor, labels: torch.Tensor) -> int:
    """
    Calculate the number of correct predictions in the given batch

    Arguments
    ---------
    outputs: The results produced by the model
    labels: The ground truth labels for the batch

    Returns
    -------
    num_correct: The number of correct predictions in the batch
    """
    predictions = sigmoid_to_predictions(outputs)
    cpu_labels = labels.clone().cpu()
    num_correct = accuracy_score(cpu_labels, predictions.cpu())

    return num_correct


def initialize_neptune(config: dict) -> None:
    """
    Connect to neptune server with our api key

    Arguments
    ---------
    config: The configuration dictionary for the project
    """
    username = config['username']
    project = config['project']
    qualified_name = f"{username}/{project}"
    api_token = None

    with open(config['secrets_file']) as secrets_file:
        secrets = yaml.safe_load(secrets_file)
        api_token = secrets['neptune_api_token']

    neptune.init(api_token=api_token,
                 project_qualified_name=qualified_name)


def deterministic_shuffle_set(set_: set) -> List[Any]:
    """
    random.choice does not behave deterministically when used on sets, even if a seed is set.
    This function sorts the list representation of the set and samples from it, preventing
    determinism bugs

    Arguments
    ---------
    set_: The set to shuffle

    Returns
    -------
    shuffled_list: The shuffled list representation of the original set
    """
    shuffled_list = random.sample(sorted(list(set_)), len(set_))

    return shuffled_list


def determine_subset_fraction(train_positive: int,
                              train_negative: int,
                              val_positive: int,
                              val_negative: int) -> int:
    """
    Determine the correct fraction of samples to remove from the training positive or negative
    sample pool to match the fraction of positive samples in the validation set

    Arguments
    ---------
    train_positive: The number of positive training samples
    train_negative: The number of negative training samples
    val_positive: The number of positive validation samples
    val_negative: The number of negative validation samples

    Returns
    -------
    subset_fraction: The fraction of positive or negative (determined by the calling code) samples
                     to remove
    """
    train_disease_fraction = train_positive / (train_negative + train_positive)
    val_disease_fraction = val_positive / (val_positive + val_negative)

    # If train ratio is too high, remove positive samples
    if train_disease_fraction > val_disease_fraction:
        # X / (negative + X) = val_frac. Solve for X
        target = (val_disease_fraction * train_negative) / (1 - val_disease_fraction)
        subset_fraction = target / train_positive

    elif train_disease_fraction < val_disease_fraction:
        # positive / (positive + X) = val_frac. Solve for X
        target = (train_positive - (val_disease_fraction * train_positive)) / val_disease_fraction
        subset_fraction = target / train_negative

    return subset_fraction
