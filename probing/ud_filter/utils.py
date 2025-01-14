import csv
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.model_selection import train_test_split


def filter_labels_after_split(labels: List[str]) -> List[str]:
    """Skipping those classes which have only 1 sentence???"""

    labels_repeat_dict = Counter(labels)
    n_repeat = 1  # threshold to overcome further splitting problem
    return [label for label, count in labels_repeat_dict.items() if count > n_repeat]


def subsamples_split(
    probing_dict: Dict[str, List[str]],
    partition: List[float],
    random_seed: int,
    shuffle: bool = True,
    split: List[str] = ["tr", "va", "te"],
) -> Dict[str, List[List[str]]]:
    """
    Splits data into three sets: train, validation, and test
    in the given relation
    Args:
        probing_dict: {class_label: [sentences]}
        partition: a relation that sentences should be split in. ex: [0.8, 0.1, 0.1]
        random_seed: random seed for splitting
        shuffle: if sentences should be randomly shuffled
        split: parts that data should be split to
    Returns:
        parts: {part: [[sentences], [labels]]}
    """
    num_classes = len(probing_dict.keys())
    probing_data = []
    for class_name, sentences in probing_dict.items():
        if len(sentences) > num_classes:
            for s in sentences:
                probing_data.append((s, class_name))
        else:
            print(
                f"Class {class_name} has less sentences ({len(sentences)}) "
                f"than the number of classes ({num_classes}), so it is excluded."
            )
    if not probing_data:
        raise Exception("All classes have less sentences than the number of classes")
    parts = {}
    data, labels = map(list, zip(*probing_data))
    X_train, X_test, y_train, y_test = train_test_split(
        data,
        labels,
        stratify=labels,
        train_size=partition[0],
        shuffle=shuffle,
        random_state=random_seed,
    )
    if len(partition) == 2:
        parts = {split[0]: [X_train, y_train], split[1]: [X_test, y_test]}
    else:
        filtered_labels = filter_labels_after_split(y_test)
        if len(filtered_labels) >= 2:
            train_mask = np.isin(y_train, filtered_labels)
            X_train = [X_train[i] for i in range(len(train_mask)) if train_mask[i]]
            y_train = [y_train[i] for i in range(len(train_mask)) if train_mask[i]]
            test_mask = np.isin(y_test, filtered_labels)
            X_test = [X_test[i] for i in range(len(test_mask)) if test_mask[i]]
            y_test = [y_test[i] for i in range(len(test_mask)) if test_mask[i]]

            val_size = partition[1] / (1 - partition[0])
            if len(y_test) != 0:
                X_val, X_test, y_val, y_test = train_test_split(
                    X_test,
                    y_test,
                    stratify=y_test,
                    train_size=val_size,
                    shuffle=shuffle,
                    random_state=random_seed,
                )
                parts = {
                    split[0]: [X_train, y_train],
                    split[1]: [X_test, y_test],
                    split[2]: [X_val, y_val],
                }
        else:
            raise Exception(
                f"There is not enough sentences for {partition} partition."
            )  # TODO
    return parts


def read(path: os.PathLike) -> str:
    """Reads CoNLL-U file"""
    with open(path, encoding="utf-8") as f:
        conllu_file = f.read()
    return conllu_file


def writer(
    partition_sets: Dict[str, List[List[str]]],
    task_name: str,
    language: str,
    save_path_dir: os.PathLike,
) -> Path:
    """
    Writes to a csv file
    Args:

        partition_sets: {part: [[sentences], [labels]]}
        task_name: name for the probing task (will be used in result file name)
        language: language title
        save_path_dir: path to the directory where to save

    """
    result_path = Path(Path(save_path_dir).resolve(), f"{language}_{task_name}.csv")
    with open(result_path, "w", encoding="utf-8") as newf:
        my_writer = csv.writer(newf, delimiter="\t", lineterminator="\n")
        for part in partition_sets:
            for sentence_and_ids, value in zip(*partition_sets[part]):
                sentence, ids = sentence_and_ids
                my_writer.writerow([part, value, sentence, ",".join([str(x) for x in ids])])
    return result_path


def extract_lang_from_udfile_path(
    ud_file_path: os.PathLike, language: Optional[str]
) -> str:
    """Extracts language from conllu file name"""

    if not language:
        return Path(ud_file_path).stem.split("-")[0]
    return language


def determine_ud_savepath(
    path_from_files: os.PathLike, save_path_dir: Optional[os.PathLike]
) -> Path:
    """Creates a path to save the result file (the same directory where conllu paths are stored"""

    final_path = None
    if not save_path_dir:
        final_path = path_from_files
    else:
        final_path = save_path_dir
    os.makedirs(final_path, exist_ok=True)
    return Path(final_path)


def delete_duplicates(probing_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Deletes sentences with more than one different classes of node_pattern found"""

    all_sent = [sent for cl_sent in probing_dict.values() for sent, inds in cl_sent]
    duplicates = {item for item, count in Counter(all_sent).items() if count > 1}
    new_probing_dict = {}
    for cl in probing_dict:
        new_probing_dict[cl] = [(sent, ind) for sent, ind in probing_dict[cl] if sent not in duplicates]
    return new_probing_dict


def check_query(
    node_pattern: Dict[str, Dict[str, str]],
    constraints: Dict[Tuple[str, str], Dict[Any, Any]],
) -> bool:
    """Checks that a query fits the syntax"""

    check_node_pattern(node_pattern)
    check_constraints(constraints)
    constr_nodes = set([n for p in constraints for n in p])
    nodes = set(node_pattern.keys())
    if not constr_nodes <= nodes:
        raise ValueError(
            f"Not all nodes from the constraints are defined in the node_pattern"
        )
    return True


def check_node_pattern(node_pattern: Dict[str, Dict[str, str]]) -> bool:
    """Checks that node_pattern uses only UD categories and given in a right format"""

    NODES_FIELDS = {"form", "lemma", "upos", "xpos", "exclude"}
    AVAILABLE_CATEGORIES = {
        "PronType",
        "Gender",
        "VerbForm",
        "NumType",
        "Animacy",
        "Mood",
        "Poss",
        "NounClass",
        "Tense",
        "Reflex",
        "Number",
        "Aspect",
        "Foreign",
        "Case",
        "Voice",
        "Abbr",
        "Definite",
        "Evident",
        "Typo",
        "Degree",
        "Polarity",
        "Person",
        "Polite",
        "Clusivity",
    }

    for n in node_pattern:
        npattern_fields = set(node_pattern[n].keys())
        if not npattern_fields <= (NODES_FIELDS | AVAILABLE_CATEGORIES):
            raise KeyError(
                f"Node_pattern can only include keys from this set: {NODES_FIELDS} or from the list of available "
                f"grammar categories from here: https://universaldependencies.org/u/feat/index.html"
            )

        exclude_cat = node_pattern[n].get("exclude")
        if exclude_cat:
            if not isinstance(exclude_cat, list):
                raise TypeError("Exclude features should be given in a list")
            if not set(exclude_cat) <= AVAILABLE_CATEGORIES:
                raise ValueError(
                    f"Wrong category name: {set(exclude_cat) - AVAILABLE_CATEGORIES}. Please use the same "
                    f"names as in the UD: https://universaldependencies.org/u/feat/index.html"
                )
    return True


def check_constraints(constraints: Dict[Tuple[str, str], Dict[Any, Any]]) -> bool:
    """Checks that constrains use only UD categories"""

    AVAILABLE_CATEGORIES = {
        "PronType",
        "Gender",
        "VerbForm",
        "NumType",
        "Animacy",
        "Mood",
        "Poss",
        "NounClass",
        "Tense",
        "Reflex",
        "Number",
        "Aspect",
        "Foreign",
        "Case",
        "Voice",
        "Abbr",
        "Definite",
        "Evident",
        "Typo",
        "Degree",
        "Polarity",
        "Person",
        "Polite",
        "Clusivity",
    }
    CONSTRAINT_FIELDS = {"deprels", "fconstraint", "lindist"}
    FCONSTRAINT_FIELDS = {"disjoint", "intersec"}

    for np in constraints:
        constr_types = set(constraints[np].keys())
        if not constr_types <= CONSTRAINT_FIELDS:
            raise KeyError(
                f"Wrong constraint type: {constr_types - CONSTRAINT_FIELDS}. Only {CONSTRAINT_FIELDS} can be used as "
                f"keys"
            )

        fconstr = constraints[np].get("fconstraint")
        if fconstr:
            fconst_types = set(fconstr.keys())
            if not fconst_types <= FCONSTRAINT_FIELDS:
                raise KeyError(
                    f"Wrong feature constraint type {fconst_types - FCONSTRAINT_FIELDS}. It can be only: {FCONSTRAINT_FIELDS}"
                )

            for fctype in fconstr:
                if not isinstance(fconstr[fctype], list):
                    raise TypeError(
                        f"{fctype} features should be a list of grammar categories not a {type(fconstr[fctype])}"
                    )
                if not set(fconstr[fctype]) <= AVAILABLE_CATEGORIES:
                    raise ValueError(
                        f"Wrong grammar category names: {set(fconstr[fctype]) - AVAILABLE_CATEGORIES}. Please use the "
                        f"same names as in the UD: https://universaldependencies.org/u/feat/index.html"
                    )
    return True
