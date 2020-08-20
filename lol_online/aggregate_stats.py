import sqlite3
import pandas as pd
import numpy as np
import time

from lol_online.db import get_db
from . import champion_dictionary


def oldest_game(df_games):
	ts = df_games.creation.min() // 1000
	return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts))

def newest_game(df_games):
	ts = df_games.creation.max() // 1000
	return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts))

def played_unplayed_champions(df_p):
	played = set(df_p.champion_id.apply(champion_dictionary.id_to_champion))
	unplayed = list(set(champion_dictionary.champion_to_id_dict.keys()) - played)
	played = sorted(list(played))
	return played, unplayed

def get_player_games(account_id, df_players):
	return df_players[df_players.player_id == account_id]

def players_by_team(account_id, df_p, df_players):
	# df_np are non-player
	df_np = df_players[df_players.player_id != account_id]
	# df_a are ally, df_e are enemy
	df_a = pd.merge(df_np, df_p, how='inner', left_on=['game_id','win'], right_on=['game_id','win'], suffixes=[None,'_player'])
	df_np['inverted_win'] = np.where(df_np.win, 0, 1)
	df_e = pd.merge(df_np, df_p, how='inner', left_on=['game_id','inverted_win'], right_on=['game_id','win'], suffixes=[None,'_player'])
	df_a.drop(['player_id_player', 'champion_id_player'], axis=1, inplace=True)
	df_e.drop(['player_id_player', 'champion_id_player', 'win_player', 'inverted_win'], axis=1, inplace=True)
	return df_a, df_e

def wr_by_player_champ(df_p):
#	df_p.groupby()
	pass

def wr_by_team_champ():
	# ally?
	# enemy?
	pass

def their_yasuo_vs_your_yasuo():
	pass