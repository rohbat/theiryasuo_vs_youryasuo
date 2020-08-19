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

def get_ally_games():
	pass

def get_enemy_games():
	pass

def wr_by_player_champ():
	pass

def wr_by_team_champ():
	# ally?
	# enemy?
	pass

def their_yasuo_vs_your_yasuo():
	pass