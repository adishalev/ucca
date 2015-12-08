#!/usr/bin/python3
"""
The evaluation software for UCCA layer 1.
"""
from collections import Counter

UNLABELED = "unlabeled"
WEAK_LABELED = "weak_labeled"
LABELED = "labeled"

EVAL_TYPES = (LABELED, UNLABELED, WEAK_LABELED)

# Pairs that are considered as equivalent for the purposes of evaluation
EQUIV = (("P", "S"), ("H", "C"), ("N", "L"), ("F", "R"))

# RELATORS = ["that", "than", "who", "what", "to", "how", "of"]

##############################################################################
# UTILITY METHODS
##############################################################################


def flatten_centers(p):
    """
    If there are Cs inside Cs in layer1, cancel the external C.
    :param p: Passage object to flatten
    """
    def _center_children(u):
        return [x for x in u.children if x.tag == "FN" and x.ftag == "C"]

    to_ungroup = []
    for unit in p.layer("1").all:
        if unit.tag == "FN" and unit.ftag == "C":
            parent = unit.fparent
            if len(_center_children(unit)) == 1 and\
                    (parent is None or len(_center_children(parent)) == 1):
                to_ungroup.append(unit)

    for unit in to_ungroup:
        ungroup(unit)


def ungroup(unit):
    """
    If the unit has an fparent, removes the unit and adds its children to that parent.
    :param unit: Node object to potentially remove
    """
    if unit.tag != "FN":
        return None
    fparent = unit.fparent
    if fparent is not None:
        if len(unit.parents) > 1:
            if len(unit.centers) == 1:  # if there is only one child, assign that child as the parent's child
                for e in unit.incoming:
                    if e.attrib.get("remote"):
                        e.parent.add(e.tag, unit.centers[0], edge_attrib=e.attrib)
            else:
                return None  # don't ungroup if there is more than one parent and no single center
        for e in unit.outgoing:
            fparent.add(e.tag, e.child, edge_attrib=e.attrib)
    unit.destroy()
    return fparent


def get_text(p, positions):
    return [p.layer("0").by_position(pos).text for pos in positions
            if 0 < pos <= len(p.layer("0").all)]


def to_text(p, terminal_indices):
    """
    Returns a text representation of terminals
    :param p: Passage object to get terminals from
    :param terminal_indices: indices of terminals to extract the text of
    """
    l = sorted(list(terminal_indices))
    words = get_text(p, l)
    pre_context = get_text(p, range(min(l) - 3, min(l)))
    post_context = get_text(p, range(max(l) + 1, max(l) + 3))
    return ' '.join(pre_context) + ' { ' + ' '.join(words) + ' } ' + ' '.join(post_context)


def mutual_yields(passage1, passage2, eval_type, separate_remotes=True, verbose=True):
    """
    returns a set of all the yields such that both passages have a unit with that yield.
    :param passage1: passage to compare
    :param passage2: passage to use as reference
    :param eval_type:
    1. UNLABELED: it doesn't matter what labels are there.
    2. LABELED: also requires tag match (if there are multiple units with the same yield, requires one match)
    3. WEAK_LABELED: also requires weak tag match (if there are multiple units with the same yield, requires one match)
    :param separate_remotes: whether to put remotes in a separate map
    :param verbose: whether to print mistakes that arise from common confusions
    :returns 4-tuple:
    -- the set of mutual yields
    -- the set of mutual remote yields (unless separate_remotes is False, in which case this is None)
    -- the set of yields of passage1
    -- the set of yields of passage2
    """
    def _find_mutuals(m1, m2):
        mutual_ys = set()
        error_counter = Counter()

        for y in m1.keys():
            if y in m2.keys():
                if eval_type == UNLABELED:
                    mutual_ys.add(y)
                else:
                    tags1 = set(e.tag for e in m1[y])
                    tags2 = set(e.tag for e in m2[y])
                    if eval_type == WEAK_LABELED:
                        tags1 = expand_equivalents(tags1)
                    if tags1 & tags2:  # non-empty intersection
                        mutual_ys.add(y)
                    else:
                        error_counter[(str(tags1), str(tags2))] += 1
                        if verbose:
                            if ('E' in tags1 and 'C' in tags2) or \
                               ('C' in tags1 and 'E' in tags2):
                                print('C-E', to_text(passage1, y))
                            elif ('P' in tags1 and 'C' in tags2) or \
                                 ('C' in tags1 and {'P', 'S'} & tags2):
                                print('P|S-C', to_text(passage1, y))
                            elif ('A' in tags1 and 'E' in tags2) or \
                                 ('E' in tags1 and 'A' in tags2):
                                print('A-E', to_text(passage1, y))

        return mutual_ys, error_counter

    map2, map2_remotes = create_passage_yields(passage2, not separate_remotes)

    if passage1 is None:
        return set(), set(), set(map2.keys()), set(), set(), set(map2_remotes.keys()), Counter()

    map1, map1_remotes = create_passage_yields(passage1, not separate_remotes)

    output, errors = _find_mutuals(map1, map2)
    output_remotes = None
    if separate_remotes:
        output_remotes, _ = _find_mutuals(map1_remotes, map2_remotes)
    
    return (output, set(map1.keys()), set(map2.keys()),
            output_remotes, set(map1_remotes.keys()), set(map2_remotes.keys()),
            errors)


def create_passage_yields(p, remote_terminals=False):
    """
    :param p: passage to find yields of
    :param remote_terminals: if True, regular table includes remotes
    :returns two dicts:
    1. maps a set of terminal indices (excluding punctuation) to a list of layer1 edges whose yield (excluding remotes
       and punctuation) is that set.
    2. maps a set of terminal indices (excluding punctuation) to a set of remote edges whose yield (excluding remotes
       and punctuation) is that set.
    """
    l1 = p.layer("1")
    edges = []
    for node in l1.all:
        edges.extend([e for e in node if e.tag not in ('U', 'LA', 'LR', 'T')])
   
    table_reg, table_remote = dict(), dict()
    for e in edges:
        pos = frozenset(t.position for t in e.child.get_terminals(punct=False, remotes=remote_terminals))
        if e.attrib.get("remote"):
            table_remote[pos] = table_remote.get(pos, []) + [e]
        else:
            table_reg[pos] = table_reg.get(pos, []) + [e]

    return table_reg, table_remote


def expand_equivalents(tag_set):
    """
    Returns a set of all the tags in the tag set or those equivalent to them
    :param tag_set: collection of tags (strings) to expand
    """
    return tag_set | set(t1 for t in tag_set for pair in EQUIV for t1 in pair if t in pair and t != t1)


def tag_distribution(unit_list):
    """
    Given a list of units, returns a dict that maps the tags of the units to their frequency in the text
    :param unit_list: list of Node objects
    """
    return Counter(u.tag for u in unit_list)


class Results(object):
    def __init__(self, regular_scores, remote_scores):
        self.regular_scores = regular_scores
        self.remote_scores = remote_scores

    def print(self):
        print("\nRegular Edges:")
        self.regular_scores.print()

        print("\nRemote Edges:")
        self.remote_scores.print()
        print()

    @classmethod
    def aggregate(cls, results):
        regular_scores, remote_scores = zip(*((r.regular_scores, r.remote_scores) for r in results))
        return Results(Scores.aggregate(regular_scores),
                       Scores.aggregate(remote_scores))


class Scores(object):
    def __init__(self, num_matches, num_only_guessed, num_only_ref):
        self.num_matches = num_matches
        self.num_only_guessed = num_only_guessed
        self.num_only_ref = num_only_ref
        self.num_guessed = num_matches + num_only_guessed
        self.num_ref = num_matches + num_only_ref
        self.p = "NaN" if self.num_guessed == 0 else 1.0 * num_matches / self.num_guessed
        self.r = "NaN" if self.num_ref == 0 else 1.0 * num_matches / self.num_ref
        if "NaN" in (self.p, self.r):
            self.f1 = "NaN"
        elif (self.p, self.r) == (0, 0):
            self.f1 = 0.0
        else:
            self.f1 = 2.0 * self.p * self.r / float(self.p + self.r)

    def print(self):
        print("Precision: {:.3} ({}/{})".format(self.p, self.num_matches, self.num_guessed))
        print("Recall: {:.3} ({}/{})".format(self.r, self.num_matches, self.num_ref))
        print("F1: {:.3}".format(self.f1))

    @classmethod
    def aggregate(cls, scores):
        num_matches, num_only_guessed, num_only_ref = zip(*(
            (s.num_matches, s.num_only_guessed, s.num_only_ref) for s in scores))
        return Scores(sum(num_matches),
                      sum(num_only_guessed),
                      sum(num_only_ref))


def get_scores(p1, p2, eval_type, units, fscore, errors, verbose=True):
    """
    prints the relevant statistics and f-scores. eval_type can be 'unlabeled', 'labeled' or 'weak_labeled'.
    :param p1: passage to compare
    :param p2: reference passage object
    :param eval_type: evaluation type to use, out of EVAL_TYPES
    :param units: whether to calculate and print the mutual and exclusive units in the passages
    :param fscore: whether to find and return the scores
    :param errors: whether to calculate and print the confusion matrix of errors
    :param verbose: whether to print the scores
    :returns Results object if fscore is True, otherwise None
    """
    mutual, all1, all2, mutual_rem, all1_rem, all2_rem, err_counter = \
        mutual_yields(p1, p2, eval_type, verbose=verbose)
    if verbose:
        print("Evaluation type: (" + eval_type + ")")
    res = None
    
    if verbose and units and p1 is not None:
        print("==> Mutual Units:")
        for y in mutual:
            print(get_text(p1, y))

        print("==> Only in guessed:")
        for y in all1 - mutual:
            print(get_text(p1, y))

        print("==> Only in reference:")
        for y in all2 - mutual:
            print(get_text(p1, y))

    if fscore:
        res = Results(Scores(len(mutual), len(all1 - mutual), len(all2 - mutual)),
                      Scores(len(mutual_rem), len(all1_rem - mutual_rem), len(all2_rem - mutual_rem)))
        if verbose:
            res.print()

    if verbose and errors and err_counter:
        print("\nConfusion Matrix:\n")
        for error, freq in err_counter.most_common():
            print(error[0], '\t', error[1], '\t', freq)

    return res


def evaluate(guessed_passage, ref_passage, verbose=True, units=True, fscore=True, errors=True):
    """
    :param guessed_passage: Passage object to evaluate
    :param ref_passage: reference Passage object to compare to
    :param verbose: whether to print the results
    :param units: whether to evaluate common units
    :param fscore: whether to compute precision, recall and f1 score
    :param errors: whether to print the mistakes
    :return: dictionary with entries LABELED, UNLABELED, WEAK_LABELED,
             each a Results object with regular_scores and remote_scores fields,
             each a Scores object with fields:
             num_matches, num_only_guessed, num_only_ref, num_guessed, num_ref, p, r, f1
    """
    for passage in (guessed_passage, ref_passage):
        if passage is not None:
            flatten_centers(passage)  # flatten Cs inside Cs

    res = {}
    for evaluation_type in EVAL_TYPES:
        res[evaluation_type] = get_scores(guessed_passage, ref_passage, evaluation_type,
                                          units, fscore, errors, verbose)

    return res


def average_f1(results):
    """
    Calculate the average F1 score across instances, evaluation types and regular/remote
    :param results: iterable of dictionaries of evaluation types to Results objects
    :return: a single number, the average F1
    """
    scores = [s.f1 for r in results for v in r.values()
              for s in (v.regular_scores, v.remote_scores) if s.f1 != "NaN"]
    return sum(scores) / len(scores) if scores else 0


def aggregate(results):
    """
    Aggregate Results object instances for each evaluation type
    :param results: iterable of dictionaries of evaluation type to Results objects
    :return: dictionary with a single Results object for each evaluation type
    """
    return {t: Results.aggregate(r[t] for r in results) for t in EVAL_TYPES}


def print_aggregate(results):
    """
    Print the aggregated Results objects from several evaluation types
    :param results: iterable of dictionaries of evaluation types to Results objects
    """
    for t, r in aggregate(results).items():
        print("Evaluation type: (" + t + ")")
        r.print()