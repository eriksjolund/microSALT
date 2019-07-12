from datetime import date
from flask import Flask, render_template
import logging
from io import StringIO, BytesIO

from sqlalchemy import *
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import *
from sqlalchemy.sql.expression import case, func

from microSALT import config, __version__
from microSALT.store.db_manipulator import app
from microSALT.store.orm_models import Collections, Projects, Reports, Samples, Seq_types, Versions

engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'], connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)
session = Session()
app.debug = 0
#Removes server start messages
log = logging.getLogger('werkzeug')
log.setLevel(logging.CRITICAL)


@app.route('/')
def start_page():
    projects = session.query(Projects).all()

    return render_template('start_page.html',
        projects = projects)

@app.route('/microSALT/')
def reroute_page():
    projects = session.query(Projects).all()

    return render_template('start_page.html',
        projects = projects)

@app.route('/microSALT/<project>')
def project_page(project):
    organism_groups = list()
    organism_groups.append("all")
    distinct_organisms = session.query(Samples).filter_by(CG_ID_project=project).distinct()
    for one_guy in distinct_organisms:
        if one_guy.organism not in organism_groups and one_guy.organism is not None:
            organism_groups.append(one_guy.organism)
    organism_groups.sort()
    return render_template('project_page.html',
        organisms = organism_groups,
        project = project) 

@app.route('/microSALT/<project>/qc')
def alignment_page(project):
    sample_info = gen_reportdata(project)

    return render_template('alignment_page.html',
        samples = sample_info['samples'],
        date = date.today().isoformat(),
        version = sample_info['versions'],
        threshold = config['threshold'],
        reports = sample_info['reports'],
        build = __version__)

@app.route('/microSALT/<project>/typing/<organism_group>')
def typing_page(project, organism_group):
    sample_info = gen_reportdata(project, organism_group)

    return render_template('typing_page.html',
        samples = sample_info['samples'],
        date = date.today().isoformat(),
        version = sample_info['versions'],
        threshold = config['threshold'],
        verified_organisms = config['regex']['verified_organisms'],
        reports = sample_info['reports'],
        build = __version__)


@app.route('/microSALT/STtracker/<customer>')
def STtracker_page(customer):
    sample_info = gen_reportdata(pid='all', organism_group='all')
    final_samples = list()
    for s in sample_info['samples']:
      if s.projects.Customer_ID == customer or customer == 'all':
        if s.pubmlst_ST != -1 and s.ST < 0:
          final_samples.append(s)
      
    final_samples = sorted(final_samples, key=lambda sample: \
                    (sample.CG_ID_sample)) 

    return render_template('STtracker_page.html',
        internal = final_samples)

def gen_collectiondata(collect_id=[]):
  """ Queries database using a set of samples"""
  arglist = []
  samples = session.query(Collections).filter(Collections.ID_collection==collect_id).all()
  for sample in samples:
    arglist.append("Samples.CG_ID_sample=='{}'".format(sample.CG_ID_sample))
  sample_info = session.query(Samples).filter(eval("or_({})".format(','.join(arglist))))
  sample_info = gen_add_info(sample_info)
  return sample_info

def gen_reportdata(pid='all', organism_group='all'):
  """ Queries database for all necessary information for the reports """
  if pid=='all' and organism_group=='all':
    sample_info = session.query(Samples)
  elif pid=='all':
    sample_info = session.query(Samples).filter(Samples.organism==organism_group)
  elif organism_group=='all':
    sample_info = session.query(Samples).filter(Samples.CG_ID_project==pid)
  else:
    sample_info = session.query(Samples).\
                  filter(Samples.CG_ID_project==pid, Samples.organism==organism_group)
     
  sample_info = gen_add_info(sample_info)

  reports = session.query(Reports).filter(Reports.CG_ID_project==pid).all()
  sample_info['reports'] = reports=sorted(reports, key=lambda x: x.version, reverse=True)

  return sample_info

def gen_add_info(sample_info=dict()):
  """ Enhances a sample info struct by adding ST_status, threshold info, versioning and sorting """
  #Set ST status
  output = dict()
  output['samples'] = list()
  output['versions'] = dict()

  #Sorts sample names
  sample_info = sorted(sample_info, key=lambda sample: \
                int(sample.CG_ID_sample.replace(sample.CG_ID_project, '')[1:]))

  for s in sample_info:
    s.ST_status=str(s.ST)
    if s.Customer_ID_sample.startswith('NTC') or s.Customer_ID_sample.startswith('0-') or \
    s.Customer_ID_sample.startswith('NK-') or s.Customer_ID_sample.startswith('NEG') or \
    s.Customer_ID_sample.startswith('CTRL') or s.Customer_ID_sample.startswith('Neg') or \
    s.Customer_ID_sample.startswith('blank') or s.Customer_ID_sample.startswith('dual-NTC'):
      s.ST_status = 'Kontroll (prefix)'

    if 'Kontroll' in s.ST_status or 'Control' in s.ST_status or s.ST == -1:
      s.threshold = '-'
    elif s.ST == -3:
      s.threshold = 'Failed'
    elif hasattr(s, 'seq_types') and s.seq_types != [] or s.ST == -2:
      near_hits=0
      s.threshold = 'Passed'
      for seq_type in s.seq_types:
        #Identify single deviating allele
        if seq_type.st_predictor and seq_type.identity >= config["threshold"]["mlst_novel_id"] and \
        config["threshold"]["mlst_id"] > seq_type.identity and 1-abs(1-seq_type.span) >= (config["threshold"]["mlst_span"]/100.0):
          near_hits = near_hits + 1
        elif (seq_type.identity < config["threshold"]["mlst_novel_id"] or \
              seq_type.span < (config["threshold"]["mlst_span"]/100.0)) and seq_type.st_predictor:
          s.threshold = 'Failed'

      if near_hits > 0 and s.threshold == 'Passed':
        s.ST_status = 'Unknown ({} alleles)'.format(near_hits)
    else:
      s.threshold = 'Failed'

    if not ('Control' in s.ST_status or 'Kontroll' in s.ST_status) and s.ST < 0:
      if s.ST == -1:
        s.ST_status = 'Data saknas'
      elif (s.ST <= -4 or s.ST == -2):
        s.ST_status = 'Unknown (Novel ST, Novel allele[s])'
      else:
        s.ST_status='None'

    #Resistence filter
    for r in s.resistances:
      if (r.identity >= config["threshold"]["motif_id"] and r.span >= config["threshold"]["motif_span"]/100.0):
        r.threshold = 'Passed'
      else:
        r.threshold = 'Failed'

    #Seq_type and resistance sorting
    s.seq_types=sorted(s.seq_types, key=lambda x: x.loci)
    s.resistances=sorted(s.resistances, key=lambda x: x.instance)
    output['samples'].append(s)

  versions = session.query(Versions).all()
  for version in versions:
    name = version.name[8:]
    output['versions'][name] = version.version

  return output
