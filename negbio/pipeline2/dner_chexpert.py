"""Copied and modified from CheXpert's extract

https://github.com/stanfordmlgroup/chexpert-labeler/blob/master/stages/extract.py

Original author: stanfordmlgroup
"""
import itertools
import logging
import re

import bioc
import yaml

from negbio.chexpert.constants import CARDIOMEGALY, ENLARGED_CARDIOMEDIASTINUM, OBSERVATION
from negbio.pipeline2.pipeline import Pipe


class ChexpertExtractor(Pipe):
    """Extract observations from impression sections of reports."""

    def __init__(self, phrases_file):
        with open(phrases_file) as fp:
            phrases = yaml.load(fp, yaml.FullLoader)

        self.observation2mention_phrases = {}
        self.observation2unmention_phrases = {}
        for observation, v in phrases.items():
            if 'include' in v:
                self.observation2mention_phrases[observation] = phrases[observation]['include']
            if 'exclude' in v:
                self.observation2unmention_phrases[observation] = phrases[observation]['exclude']

        logging.debug("Loading mention phrases for %s observations.",
                      len(self.observation2mention_phrases))
        logging.debug("Loading unmention phrases for %s observations.",
                      len(self.observation2unmention_phrases))
        self.add_unmention_phrases()

    def add_unmention_phrases(self):
        cardiomegaly_mentions = self.observation2mention_phrases[CARDIOMEGALY]
        enlarged_cardiom_mentions = self.observation2mention_phrases[ENLARGED_CARDIOMEDIASTINUM]
        positional_phrases = (["over the", "overly the", "in the"],
                              ["", " superior", " left", " right"])
        positional_unmentions = \
            [e1 + e2
             for e1 in positional_phrases[0]
             for e2 in positional_phrases[1]]

        cardiomegaly_unmentions = \
            [e1 + " " + e2.replace("the ", "")
             for e1 in positional_unmentions
             for e2 in cardiomegaly_mentions
             if e2 not in ["cardiomegaly", "cardiac enlargement"]]

        enlarged_cardiomediastinum_unmentions = \
            [e1 + " " + e2
             for e1 in positional_unmentions
             for e2 in enlarged_cardiom_mentions]

        self.observation2unmention_phrases[CARDIOMEGALY] = cardiomegaly_unmentions
        self.observation2unmention_phrases[ENLARGED_CARDIOMEDIASTINUM] = \
            enlarged_cardiomediastinum_unmentions

    def overlaps_with_unmention(self, sentence, observation, start, end):
        """Return True if a given match overlaps with an unmention phrase."""
        unmention_overlap = False
        unmention_list = self.observation2unmention_phrases.get(observation, [])
        for unmention in unmention_list:
            unmention_matches = re.finditer(unmention, sentence.text)
            for unmention_match in unmention_matches:
                unmention_start, unmention_end = unmention_match.span(0)
                if start < unmention_end and end > unmention_start:
                    unmention_overlap = True
                    break  # break early if overlap is found
            if unmention_overlap:
                break  # break early if overlap is found

        return unmention_overlap

    def __call__(self, document, *args, **kwargs):
        annotation_index = itertools.count()
        for passage in document.passages:
            for sentence in passage.sentences:
                obs_phrases = self.observation2mention_phrases.items()
                for observation, phrases in obs_phrases:
                    for phrase in phrases:
                        matches = re.finditer(phrase, sentence.text)
                        for match in matches:
                            start, end = match.span(0)
                            if self.overlaps_with_unmention(sentence, observation, start, end):
                                continue
                            annotation = bioc.BioCAnnotation()
                            annotation.id = str(next(annotation_index))
                            annotation.infons['term'] = phrase
                            annotation.infons[OBSERVATION] = observation
                            annotation.infons['annotator'] = 'CheXpert labeler'
                            annotation.add_location(bioc.BioCLocation(sentence.offset + start,
                                                                      end - start))
                            annotation.text = sentence.text[start:end]
                            passage.annotations.append(annotation)
        return document
