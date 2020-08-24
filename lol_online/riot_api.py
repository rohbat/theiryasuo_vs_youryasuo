import time
from collections import Counter
import numpy as np
import pandas as pd
# import matplotlib.pyplot as plt
# from scipy import stats
# import sqlite3

from riotwatcher import LolWatcher, ApiError
from .api_key import API_KEY

# from champions_dict import *


# global
REGION = 'na1'

def get_matchlist(account_id, region=REGION):
	''' retrieves list of all matches for the given account id and returns as a dataframe '''
	watcher = LolWatcher(API_KEY)
	matches = []
	i = 0
	# queue ids limit the games to 5v5 sr (norms, draft, flex, soloq, clash)
	valid_queue_ids = [400, 420, 430, 440, 700]

	print('fetching matchlist:')
	# matches.append(watcher.match.matchlist_by_account(region, account_id, begin_index=0, end_index=10))
	while True:
		try:
			match = watcher.match.matchlist_by_account(region, account_id, queue=valid_queue_ids, begin_index=100*i)
			if match['matches']:
				matches.append(match)
				i += 1
				time.sleep(.1)
				print((i - 1) * 100, '/ ?')
			else:
				break
		except:
			pass
	

	all_matches = [m for match in matches for m in match['matches']]
	df = pd.DataFrame(all_matches)
	print(len(df), '/', len(df))
	df.rename({'timestamp':'creation', 'gameId': 'game_id'}, axis=1, inplace=True)
	df.set_index('game_id', inplace=True)
	df.drop(['season', 'role', 'lane', 'platformId', 'champion'], axis=1, inplace=True)
	df.sort_index(inplace=True)
	return df
	'''
	columns:
		platformId -> might eventually want but dropped for now
		gameId -> game_id (index)
		champion -- potentially useful but dropped for now
		queue
		season -- unreliable, dropped
		timestamp -> creation
		role -- unreliable, dropped
		lane -- unreliable, dropped
	'''

def get_timelines(game_ids, region=REGION):
	''' retrieves detailed reports of all match timelines in the given matchlist and returns as a dataframe '''
	watcher = LolWatcher(API_KEY)
	timelines = []
	game_ids_success = []
	failed = []

	print('fetching timelines:')
	# better way to try 3 times??
	for i, game_id in enumerate(game_ids):
		try:
			timelines.append(watcher.match.timeline_by_match(region, game_id))
			game_ids_success.append(game_id)
		except:
			time.sleep(1.5)
			try:
				timelines.append(watcher.match.timeline_by_match(region, game_id))
				game_ids_success.append(game_id)
			except:
				time.sleep(1.5)
				try:
					timelines.append(watcher.match.timeline_by_match(region, game_id))
					game_ids_success.append(game_id)
				except:
					failed.append(game_id)
		if not i % 50:
			print(i, '/', len(game_ids))
		time.sleep(1.5)
	print(len(game_ids_success), '/', len(game_ids_success))
	if failed:
		print('game ids failed:', failed)

	df_tl = pd.DataFrame(timelines, index=game_ids_success)
	df_tl.index.rename('game_id', inplace=True)
	df_tl.sort_index(inplace=True)
	return df_tl


def get_forfeits(df, region=REGION):
	watcher = LolWatcher(API_KEY)
	df_tl = get_timelines(df.index.values, region)

	blue_nexus_turrets_destroyed = []
	red_nexus_turrets_destroyed = []
	for game in df_tl.loc[df_tl.index.values, 'frames']:
		# nexus turrets named by their x-coord--blue is 1748 and 2177--red is 12611 and 13052
		nexus_turrets = {1748: False, 2177: False, 12611: False, 13052: False}
		for frame in game:
			for event in frame['events']:
				if event['type'] == 'BUILDING_KILL' and event['towerType'] == 'NEXUS_TURRET':
					nexus_turrets[event['position']['x']] = True
		blue_nexus_turrets_destroyed.append(nexus_turrets[1748] and nexus_turrets[2177])
		red_nexus_turrets_destroyed.append(nexus_turrets[12611] and nexus_turrets[13052])
	blue_nexus_turrets_destroyed = pd.Series(blue_nexus_turrets_destroyed, index=df_tl.index)
	red_nexus_turrets_destroyed = pd.Series(red_nexus_turrets_destroyed, index=df_tl.index)

	forfeit = ~((red_nexus_turrets_destroyed & (df.winner == 100)) | \
						(blue_nexus_turrets_destroyed & (df.winner == 200)))
	return forfeit.apply(int)

def get_matches(df, region=REGION):
	watcher = LolWatcher(API_KEY)
	matches = []
	game_ids_success = []
	failed = []

	print('fetching matches:')
	# better way to try 3 times??
	for i, game_id in enumerate(df.index.values):
		try:
			matches.append(watcher.match.by_id(region, game_id))
			game_ids_success.append(game_id)
		except:
			time.sleep(1.5)
			try:
				matches.append(watcher.match.by_id(region, game_id))
				game_ids_success.append(game_id)
			except:
				time.sleep(1.5)
				try:
					matches.append(watcher.match.by_id(region, game_id))
					game_ids_success.append(game_id)
				except:
					failed.append(game_id)
		if not i % 50:
			print(i, '/', len(df))
		time.sleep(1.5)
	print(len(game_ids_success), '/', len(game_ids_success))
	if failed:
		print('game ids failed:', failed)

	df_m = pd.DataFrame(matches)
	df_m.index = df_m.gameId
	df_m.index.rename('game_id', inplace=True)
	df_m.drop('gameId', axis=1, inplace=True)
	df_m.sort_index(inplace=True)
	return df_m

def filter_remakes(df):
	'''
	returns tuple (full-length games, remakes)
	'''
	if 'duration' in df.columns:
		remake_mask = df.duration > 300
	elif 'gameDuration' in df.columns:
		remake_mask = df.gameDuration > 300
	print(df[remake_mask])
	print(df[~remake_mask])
	return df[remake_mask], df[~remake_mask]

def get_account_id(account_name):
	watcher = LolWatcher(API_KEY)
	account = watcher.summoner.by_name(REGION, account_name)
	return account['accountId']

def main():
	pass

if __name__ == '__main__':
	main()
