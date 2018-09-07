"""Compares existing organism references with available and updates as needed
   By: Isak Sylvin, @sylvinite"""

#!/usr/bin/env python
import json
import os
import re
import shutil
import subprocess
import urllib.request

from bs4 import BeautifulSoup
from microSALT.store.db_manipulator import DB_Manipulator
from microSALT.store.lims_fetcher import LIMS_Fetcher

class Referencer():

  def __init__(self, config, log):
    self.config = config
    self.logger = log
    self.db_access = DB_Manipulator(config, log)
    self.updated = list()
    #Fetch names of existing refs
    self.refs = self.db_access.get_profiles()
    organisms = self.refs.keys()
    self.organisms = [*organisms]
    self.lims=LIMS_Fetcher(config, log)

  def identify_new(self, cg_id, project=False):
   neworgs = list()
   if project:
     samplenames = self.lims.samples_in_project(cg_id)
     for cg_sampleid in samplenames:
       self.lims.load_lims_sample_info(cg_sampleid)
       refname = self.lims.get_organism_refname(cg_sampleid)
       if refname not in self.organisms and refname not in neworgs:
         neworgs.append(self.lims.data['organism'])
     for org in neworgs:
       self.add_pubmlst(org)
   else:
     self.lims.load_lims_sample_info(cg_id)
     refname = self.lims.get_organism_refname(cg_id)
     if refname not in self.organisms:
       self.add_pubmlst(org)

  def update_refs(self):
    """Updates all references. Order is important, since no object is updated twice"""
    self.fetch_pubmlst()
    self.fetch_external()
    self.fetch_resistances()

  def fetch_external(self):
    """ Updates reference for data that IS ONLY LINKED to pubMLST """
    prefix = "https://pubmlst.org"
    query = urllib.request.urlopen("{}/data/".format(prefix))
    soup = BeautifulSoup(query, 'html.parser')
    tr_sub = soup.find_all("tr", class_="td1")

    # Only search every other instance
    iterator = iter(tr_sub)
    unfound = True
    try:
      while unfound:
        entry = iterator.__next__()
        # Gather general info from first object
        sample = entry.get_text().split('\n')
        organ = sample[1].lower().replace(' ', '_')
        # In order to get ecoli #1
        if "escherichia_coli" in organ and "#1" in organ:
          organ = organ[:-2]
        currver = self.db_access.get_version("profile_{}".format(organ))
        profile_no = re.search('\d+', sample[2]).group(0)
        if organ in self.organisms and organ.replace("_", " ") not in self.updated and profile_no > currver:
          # Download definition files
          st_link = prefix + entry.find_all("a")[1]['href']
          output = "{}/{}".format(self.config['folders']['profiles'], organ)
          urllib.request.urlretrieve(st_link, output)
          # Update database
          self.db_access.upd_rec({'name':"profile_{}".format(organ)}, 'Versions', {'version':profile_no})
          self.db_access.reload_profiletable(organ)
          # Gather loci from second object
          entry = iterator.__next__()
          # Clear existing directory and download allele files
          out = "{}/{}".format(self.config['folders']['references'], organ)
          shutil.rmtree(out)
          os.makedirs(out)
          for loci in entry.find_all("a"):
            loci = loci['href']
            lociname = os.path.basename(os.path.normpath(loci))
            input = prefix + loci
            urllib.request.urlretrieve(input, "{}/{}".format(out, lociname))
        else:
          iterator.__next__()
    except StopIteration:
      pass

  def fetch_resistances(self):
    cwd = os.getcwd()
    url = "https://bitbucket.org/genomicepidemiology/resfinder_db.git"
    hiddensrc ="{}/.resfinder_db/".format(self.config['folders']['resistances'])
    if not os.path.isdir(hiddensrc):
      self.logger.info("resFinder database not found. Fetching..")
      cmd = "git clone {} --quiet".format(url)
      process = subprocess.Popen(cmd.split(),cwd=self.config['folders']['resistances'], stdout=subprocess.PIPE)
      output, error = process.communicate()
      cmd = "mv {}/resfinder_db {}".format(self.config['folders']['resistances'], hiddensrc)
      process = subprocess.Popen(cmd.split())
      output, error = process.communicate()
    else:
      cmd = "git pull"
    process = subprocess.Popen(cmd.split(),cwd=hiddensrc, stdout=subprocess.PIPE)
    output, error = process.communicate()
    if 'Already up-to-date.' in str(output):
      self.logger.info("resFinder database at latest version.")
    else:
      self.logger.info("resFinder database updated: {}".format(output))

  def existing_organisms(self):
    """ Returns list of all organisms currently added """
    return self.organisms

  def add_pubmlst(self, organism):
    """ Checks pubmlst for references of given organism and downloads them """
    #Organism must be in binomial format and only resolve to one hit
    organism = organism.lower().replace(' ', '_')
    if organism in self.organisms:
      self.logger.info("Organism {} already stored in microSALT".format(organism))
      return
    db_query = self.query_pubmlst()

    #Doublecheck organism name is correct and unique
    counter = 0.0 
    for item in db_query:
      for subtype in item['databases']:
        if organism.replace('_', ' ') in subtype['description'].lower():
          #Seqdef always appear after isolates, so this is fine
          seqdef_url = subtype['href']
          counter += 1.0
    if counter > 2:
      self.logger.info("Organism request resolved to {} organisms. Please be more stringent".format(counter/2))
      return
    elif counter < 1:
      self.logger.info("Unable to find requested organism in pubMLST database")
      return
    else:
      self.download_pubmlst(organism, seqdef_url)

  def query_pubmlst(self):
    """ Returns a json object containing all organisms available via pubmlst.org """
    # Example request URI: http://rest.pubmlst.org/db/pubmlst_neisseria_seqdef/schemes/1/profiles_csv
    seqdef_url = dict()
    databases = "http://rest.pubmlst.org/db"
    db_req = urllib.request.Request(databases)
    with urllib.request.urlopen(db_req) as response:
      db_query = json.loads(response.read().decode('utf-8'))
    return db_query

  def download_pubmlst(self, organism, subtype_href):
    """ Downloads ST and loci for a given organism stored on pubMLST if it is more recent. Returns update date """
    organism = organism.lower().replace(' ', '_')

    #Pull version
    ver_req = urllib.request.Request("{}/schemes/1/profiles".format(subtype_href))
    with urllib.request.urlopen(ver_req) as response:
        ver_query = json.loads(response.read().decode('utf-8'))
    currver = self.db_access.get_version("profile_{}".format(organism))
    if ver_query['last_updated'] <= currver:
      return currver

    #Pull ST file
    st_target = "{}/{}".format(self.config['folders']['profiles'], organism)
    input = "{}/schemes/1/profiles_csv".format(subtype_href)
    urllib.request.urlretrieve(input, st_target)
    #Pull locus files
    loci_input="{}/schemes/1".format(subtype_href)
    loci_req = urllib.request.Request(loci_input)
    with urllib.request.urlopen(loci_req) as response:
     loci_query = json.loads(response.read().decode('utf-8'))

    output = "{}/{}".format(self.config['folders']['references'], organism)
    if(os.path.isdir(output)):
      shutil.rmtree(output)
    os.makedirs(output)

    for locipath in loci_query['loci']:
          loci = os.path.basename(os.path.normpath(locipath))
          urllib.request.urlretrieve("{}/alleles_fasta".format(locipath), "{}/{}.tfa".format(output, loci))
    return ver_query['last_updated']

  def fetch_pubmlst(self):
    """ Updates reference for data that is stored on pubMLST """
    seqdef_url=dict()
    db_query = self.query_pubmlst()
    
    # Fetch seqdef locations 
    for name in self.organisms:
      for item in db_query:
        for subtype in item['databases']:
          if name.replace('_', ' ') in subtype['description'].lower():
            #Seqdef always appear after isolates, so this is fine
            self.updated.append(name.replace('_', ' '))
            seqdef_url[name] = subtype['href']

    for key, val in seqdef_url.items():
      ver = self.download_pubmlst(key, val)
      self.db_access.upd_rec({'name':'profile_{}'.format(key)}, 'Versions', {'version':ver})
      self.logger.info('Table profile_{} set to version {}'.format(key, ver))
