"""This is the main entry point of locioser. Current commands are analyze and store
   Heavy WIP
   By: Isak Sylvin, @sylvinite"""

#!/usr/bin/env python

import click
import os
import pdb
import yaml

from pkg_resources import iter_entry_points
from locioser import __version__
from locioser import job_creator
from locioser import scraper

@click.group()
@click.version_option(__version__)
@click.pass_context
def root(ctx):
    """ Fundamental MLST pipeline """
    with open("{}/config.yml".format(os.path.dirname(os.path.realpath(__file__))), 'r') as conf:
      config = yaml.load(conf)
    ctx.obj = config

@root.command()
@click.argument('indir')
@click.pass_context
def create_job(ctx, indir):
    boss = job_creator.Job_Creator(indir, ctx.obj)
    boss.create_job()

@root.command()
@click.argument('infile')
@click.pass_context
def scrape(ctx, infile):
  garbageman = scraper.Scraper(infile, ctx.obj)
  garbageman.scrape_blast_loci()