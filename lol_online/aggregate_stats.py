import sqlite3
import pandas as pd
import numpy as np
import time
from scipy import stats
import matplotlib.pyplot as plt

import io
import base64
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure

from flask import render_template

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

def their_yasuo_vs_your_yasuo(df_awr, df_ewr):
	df_yas = pd.DataFrame({'games_with': df_awr.games, 'winrate_with': df_awr.winrate,
				'games_agaisnst': df_ewr.games, 'winrate_against': df_ewr.winrate})
	df_yas['delta_winrate'] = df_yas.winrate_with - (1 - df_yas.winrate_against)
	return df_yas.sort_values(by='delta_winrate')

def average_game_durations(df_pg):
	'''
	returns multiindexed dataframe of average game durations grouped by win and forfeit
	also has overall/overall for overall average duration
	'''
	df = pd.DataFrame()
	df['duration'] = df_pg.duration.copy()
	df['win'] = np.where(df_pg.win, 'win', 'loss')
	df['forfeit'] = np.where(df_pg.forfeit, 'forfeit', 'non-forfeit')

	format_duration = lambda x: '{}:{:02d}'.format(int(x/60), int(x%60))
	df_duration = df.groupby(['forfeit','win']).mean().loc[:,['duration']]
	df_duration['duration'] = df_duration.duration.apply(format_duration)
	df_duration.rename({'duration':'average_duration'}, axis=1, inplace=True)
	df_duration.loc[('overall','overall'),:] = format_duration(df.duration.mean())

	return df_duration

def game_durations_plot(df_pg):
	'''
	generates figure of game durations with three suplots for all, forfeit and non-forfeit games
	converts figure to html-rederable image and returns
	reference for this conversion:
		https://gitlab.com/snippets/1924163
		https://stackoverflow.com/questions/50728328/python-how-to-show-matplotlib-in-flask

	'''
	plt.style.use('ggplot')
	fig, ax = plt.subplots(3, sharex=True)
	ax[0].set_title('all')
	ax[1].set_title('non-forfeits')
	ax[2].set_title('forfeits')

	low_min = df_pg.duration.min() // 60
	low_bin = low_min * 60
	high_min = df_pg.duration.max() // 60
	high_bin = (high_min + 1) * 60
	nbins = (high_min - low_min) + 2
	bins = np.linspace(low_bin, high_bin, nbins)

	# populate the subplots
	game_durations_subplot(df_pg, ax[0], bins, None)
	game_durations_subplot(df_pg, ax[1], bins, False)
	game_durations_subplot(df_pg, ax[2], bins, True)

	# annoying lambda functions to determine min and max bounds/ticks for x axis
	low_tick = lambda x: (((x - 1) // 5) + 1) * 5
	high_tick = lambda x: ((x // 5) * 5) + 5
	low_bound = lambda x: -x % 5
	high_bound = lambda x: x - (x % 5) - 10

	plt.xticks(range(low_bound(low_min), high_bound(high_min), 5), range(low_tick(low_min), high_tick(high_min), 5)) # will break for games > 10 hours xD
	plt.xlabel('game duration (min)')
	# plt.ylabel('count games')
	plt.legend()
	# plt.show()

	png_image = io.BytesIO()
	FigureCanvas(fig).print_png(png_image)
	png_image_b64_string = 'data:image/png;base64,'
	png_image_b64_string += base64.b64encode(png_image.getvalue()).decode('utf8')
	return render_template('test_img.html', image=png_image_b64_string)

def game_durations_subplot(df_pg, axis, bins, forfeit=None):
	'''
	fills subplots of figure generated in game_durations_plot
	'''
	if forfeit:
		df = df_pg[df_pg.forfeit == 1]
	elif forfeit == False:
		df = df_pg[df_pg.forfeit == 0]
	else:
		df = df_pg

	win = df[df.win == 1]
	loss = df[df.win == 0]

	all_cut = pd.cut(df_pg.duration, bins=bins, right=False)
	win_cut = pd.cut(win.duration, bins=bins, right=False)
	loss_cut = pd.cut(loss.duration, bins=bins, right=False)

	win.groupby(win_cut).win.count().plot(ax=axis, label='wins', legend=True)
	loss.groupby(loss_cut).win.count().plot(ax=axis, label='losses', legend=True)
