"""This is the main entry point of microSALT. Current commands are analyze and store
   Heavy WIP
   By: Isak Sylvin, @sylvinite"""

#!/usr/bin/env python

import click
import os
import pdb
import yaml
import logging

from pkg_resources import iter_entry_points
from microSALT import __version__
from microSALT import job_creator
from microSALT import scraper
from microSALT import exporter

@click.group()
@click.version_option(__version__)
@click.pass_context
def root(ctx):
    ctx.obj = {}
    """ Fundamental MLST pipeline """
    install_dir = os.path.dirname(os.path.realpath(__file__))
    #Load config yaml
    with open("{}/config.yml".format(install_dir), 'r') as conf:
      config = yaml.load(conf)
    ctx.obj['config'] = config

    #Defining logging here. Might want to move it later.
    logger = logging.getLogger('main_logger')
    logger.setLevel(logging.DEBUG)
   
    fh = logging.FileHandler("{}/{}".format(install_dir, "microSALT.log"))
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    logger.addHandler(ch)
    ctx.obj['log'] = logger
 
@root.command()
@click.argument('indir')
@click.argument('organism')
@click.pass_context
def create_job(ctx, indir, organism):
    boss = job_creator.Job_Creator(indir, organism, ctx.obj['config'], ctx.obj['log'])
    boss.create_job()

@root.command()
@click.argument('infile')
@click.pass_context
def scrape(ctx, infile):
  garbageman = scraper.Scraper(infile, ctx.obj['config'])
  garbageman.scrape_blast_loci()

@root.command()
@click.pass_context
def export(ctx):
  ferryman = exporter.Exporter(ctx.obj['config'])
  ferryman.std_export()
