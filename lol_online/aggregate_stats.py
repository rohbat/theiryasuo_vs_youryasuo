import sqlite3
import pandas as pd
import numpy as np
import time
from scipy import stats

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
	# df_np are non-player, df_a are ally, df_e are enemy
	df_np = df_players[df_players.player_id != account_id]
	df_a = pd.merge(df_np, df_p, how='inner', left_on=['game_id','win'], right_on=['game_id','win'], suffixes=[None,'_player'])
	# created inverted_win in order to inner join as pandas cannot yet join on inequalities
	df_np['inverted_win'] = np.where(df_np.win, 0, 1)
	df_e = pd.merge(df_np, df_p, how='inner', left_on=['game_id','inverted_win'], right_on=['game_id','win'], suffixes=[None,'_player'])
	df_a.drop(['player_id_player', 'champion_id_player'], axis=1, inplace=True)
	# in df_e, win state is flipped in order to align with current player's perspective
	df_e.drop(['player_id_player', 'champion_id_player', 'win_player', 'win'], axis=1, inplace=True)
	df_e.rename({'inverted_win': 'win'}, axis=1, inplace=True)
	print(df_e.columns)
	return df_a, df_e

def join_player_games(df_p, df_games):
	df_pg = pd.merge(df_games, df_p, how='inner', left_index=True, right_on='game_id')
	df_pg.set_index('game_id', inplace=True)
	df_pg.drop(['queue','creation','player_id'], axis=1, inplace=True)
	df_pg['player_team'] = np.where(df_pg.win, df_pg.winner, np.where(df_pg.winner==100, 200, 100))
	return df_pg

def winrate_by_champ(df):
	grouped = df.groupby('champion_id').win
	df_g = pd.DataFrame({'games': grouped.count(), 'wins': grouped.sum()})
	# df_g = pd.DataFrame()
	# df_g['games'] = grouped.count()
	# df_g['wins'] = grouped.sum()
	df_g['losses'] = df_g.games - df_g.wins
	df_g['winrate'] = df_g.wins / df_g.games
	p_value = lambda champion: stats.binom_test(champion.wins, champion.games) # p = 0.05
	df_g['p_value'] = df_g.apply(p_value, axis=1)
	df_g.index = pd.Series(df_g.index).apply(champion_dictionary.id_to_champion)
	return df_g

def blue_red_winrate(df_pg):
	grouped = df_pg.groupby('player_team')
	df_brwr = pd.DataFrame({'games': grouped.win.count(), 'wins': grouped.win.sum()})
	df_brwr['losses'] = df_brwr.games - df_brwr.wins
	df_brwr['winrate'] = df_brwr.wins / df_brwr.games
	p_value = lambda side: stats.binom_test(side.wins, side.games)
	df_brwr['p_value'] = df_brwr.apply(p_value, axis=1)
	return df_brwr

def game_durations(df_pg):
	# WORK ON THIS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	return df_pg.sort_values(by='duration')


def their_yasuo_vs_your_yasuo(df_awr, df_ewr):
	df_yas = pd.DataFrame({'games_with': df_awr.games, 'winrate_with': df_awr.winrate,
				'games_agaisnst': df_ewr.games, 'winrate_against': df_ewr.winrate})
	df_yas['delta_winrate'] = df_yas.winrate_with - (1 - df_yas.winrate_against)
	return df_yas.sort_values(by='delta_winrate')