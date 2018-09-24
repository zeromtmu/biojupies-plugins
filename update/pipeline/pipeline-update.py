#################################################################
#################################################################
############### BioJupies Plugin Updater ################
#################################################################
#################################################################
##### Author: Denis Torre
##### Affiliation: Ma'ayan Laboratory,
##### Icahn School of Medicine at Mount Sinai

#############################################
########## 1. Load libraries
#############################################
##### 1. Python modules #####
from ruffus import *
import sys, glob, json, os, pymysql
import pandas as pd
from sqlalchemy import create_engine
pymysql.install_as_MySQLdb()

##### 2. Custom modules #####
# Pipeline running

#############################################
########## 2. General Setup
#############################################
##### 1. Variables #####
tool_metadata = glob.glob('../library/analysis_tools/*/*_metadata.json')
option_metadata = glob.glob('../library/core_scripts/*/*_metadata.json')
engine = create_engine(os.environ['SQLALCHEMY_DATABASE_URI'])

##### 2. R Connection #####

#######################################################
#######################################################
########## S1. Prepare Tables
#######################################################
#######################################################

#############################################
########## 1. Tool Table
#############################################

@follows(mkdir('s1-tables.dir'))

@merge(tool_metadata,
	   's1-tables.dir/tool-table.txt')

def createToolTable(infiles, outfile):

	# Get updated tools
	new_tools = []
	for infile in infiles:
		with open(infile) as openfile:
			new_tools.append(json.load(openfile))
			
	# Create table
	tool_table = pd.DataFrame(new_tools).set_index('tool_string').drop('parameters', axis=1)

	# Read IDs
	tool_ids = pd.read_sql_query('SELECT id, tool_string FROM tool', engine).set_index('tool_string').to_dict()['id']

	# Update IDs
	for tool_string in tool_table.index:
		if not tool_ids.get(tool_string):
			tool_ids[tool_string] = max(tool_ids.values())+1

	# Add IDs
	tool_table['id'] = [tool_ids[x] for x in tool_table.index]

	# Write
	tool_table.to_csv(outfile, sep='\t')

#############################################
########## 2. Parameter Table
#############################################

@files([createToolTable, tool_metadata],
       ['s1-tables.dir/parameter-table.txt', 's1-tables.dir/parameter_value-table.txt'])

def createParameterTable(infiles, outfiles):

	# Split infiles
	table_file, json_files = infiles

	# Read IDs
	tool_ids = pd.read_table(table_file).set_index('tool_string')['id'].to_dict()

	# Get updated parameters
	parameters = []
	for infile in json_files:
		with open(infile) as openfile:
			tool_metadata = json.load(openfile)
			for parameter in tool_metadata['parameters']:
				parameter.update({'tool_fk': tool_ids[tool_metadata['tool_string']]})
				parameters.append(parameter)

	# Make parameter table
	parameter_table = pd.DataFrame(parameters)
	parameter_table['id'] = [x+1 for x in parameter_table.index]

	# Add values
	for index, rowData in parameter_table.iterrows():
		for value in rowData['values']:
			value.update({'parameter_fk': rowData['id']})

	# Parameter value table
	parameter_value_table = pd.DataFrame([y for x in parameter_table.pop('values') for y in x])
	parameter_value_table['id'] = [x+1 for x in parameter_value_table.index]

	# Write tables
	parameter_table.to_csv(outfiles[0], sep='\t', index=False)
	parameter_value_table.to_csv(outfiles[1], sep='\t', index=False)

#############################################
########## 3. Options Table
#############################################

@merge(option_metadata,
	   's1-tables.dir/core_scripts-table.txt')

def createOptionTable(infiles, outfile):

	# Get options
	options = []
	for infile in infiles:
		with open(infile) as openfile:
			options += json.load(openfile)

	# Create dataframe
	option_dataframe = pd.DataFrame(options)
	option_dataframe['id'] = [x+1 for x in option_dataframe.index]

	# Write
	option_dataframe.to_csv(outfile, sep='\t', index=False)

#######################################################
#######################################################
########## S2. Update
#######################################################
#######################################################

#############################################
########## 1. Upload Tables
#############################################

@follows(mkdir('s2-upload.dir'))

@merge(glob.glob('s1-tables.dir/*-table.txt'),
	   's2-upload.dir/upload.txt')

def uploadTables(infiles, outfile):

	# Initialize table dict
	table_dict = {}

	# 3Loop through infiles
	for infile in infiles:

		# Get table name
		table_name = os.path.basename(infile).split('-')[0]

		# Read table
		print(table_name)
		table_dict[table_name] = pd.read_table(infile, index_col='id')

	# Loop through tables
	for table_name in ['tool', 'parameter', 'parameter_value', 'core_scripts']:

		# Upload
		engine.execute('SET FOREIGN_KEY_CHECKS=0;')
		engine.execute('TRUNCATE TABLE {}; '.format(table_name))
		engine.execute('SET FOREIGN_KEY_CHECKS=1;')
		table_dict[table_name].fillna('').to_sql(table_name, engine, if_exists='append')

##################################################
##################################################
########## Run pipeline
##################################################
##################################################
pipeline_run([sys.argv[-1]], multiprocess=1, verbose=1)
print('Done!')