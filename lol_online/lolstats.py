from flask import (
	Blueprint, flash, g, redirect, render_template, request, url_for
)
# from werkzeug.exceptions import abort
import sqlite3
import pandas as pd
import numpy as np

from lol_online.db import get_db

from . import riot_api, aggregate_stats

lolstats = Blueprint('lolstats', __name__)

@lolstats.route('/api_key')
def api_key():
	return riot_api.API_KEY

@lolstats.route('/read_games')
def read_games():
	''' lists all games currently in database '''
	db = get_db()
	df = pd.read_sql('SELECT * FROM games', con=db)
	return df.to_html(index=False)

@lolstats.route('/read_players')
def read_players():
	''' lists all players currently in database '''
	db = get_db()
	df = pd.read_sql('SELECT * FROM players', con=db)
	return df.to_html(index=False)

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@lolstats.route('/test')
def test(account_name='omicronalpha'):
	create_temporary_tables()
	account_id = riot_api.get_account_id(account_name)

	df_games, df_players = collect_games_players_dataframes(account_id)
	df_p = aggregate_stats.get_player_games(account_id, df_players)
	df_a, df_e = aggregate_stats.players_by_team(account_id, df_p, df_players)
	df_pwr = aggregate_stats.winrate_by_champ(df_p)
	df_awr = aggregate_stats.winrate_by_champ(df_a)
	df_ewr = aggregate_stats.winrate_by_champ(df_e)

	oldest = aggregate_stats.oldest_game(df_games)
	newest = aggregate_stats.newest_game(df_games)
	# df_p is the players table only including entires played by desired player

	# df_*wr are player, ally, enemy winrates
	df_pg = aggregate_stats.join_player_games(df_p, df_games)

	df_brwr = aggregate_stats.blue_red_winrate(df_pg)

	df_gd = aggregate_stats.game_durations(df_pg)
	df_yas = aggregate_stats.their_yasuo_vs_your_yasuo(df_awr, df_ewr)



	# print(df_pwr, df_pwr.games.sum(), df_pwr.wins.sum(), df_pwr.losses.sum())
	# print(df_awr, df_awr.games.sum(), df_awr.wins.sum(), df_awr.losses.sum())
	# print(df_ewr, df_ewr.games.sum(), df_ewr.wins.sum(), df_ewr.losses.sum())
	drop_temporary_tables()
	return '<h1>TEST</h1>' + df_pwr.sort_values('p_value').to_html()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def collect_games_players_dataframes(account_id):
	db = get_db()

	df_games, df_players, df_remakes = build_new_dataframe_tables(account_id)

	if not df_games.empty:
		df_games.to_sql('new_games', con=db, if_exists='append', index=True)
		df_games.to_sql('games', con=db, if_exists='append', index=True)
		df_games = df_games.append(pd.read_sql('SELECT * FROM preexisting_games', con=db, index_col='game_id'))

		df_players.to_sql('new_players', con=db, if_exists='append', index=False)
		df_players.to_sql('players', con=db, if_exists='append', index=False)
		df_players = df_players.append(pd.read_sql('SELECT * FROM preexisting_players', con=db), ignore_index=True)

		print(pd.read_sql('SELECT * FROM preexisting_players', con=db))
	else:
		df_games = pd.read_sql('SELECT * FROM preexisting_games', con=db, index_col='game_id')
		df_players = pd.read_sql('SELECT * FROM preexisting_players', con=db)

	if not df_remakes.empty:
		df_remakes.to_sql('games', con=db, if_exists='append', index=True)


	return df_games, df_players


def build_new_dataframe_tables(account_id):
	'''
	constructs and returns df_games and df_players from game data newly collected from riot
	these will be used for analysis and then inserted into the database
	'''

	df_games = riot_api.get_matchlist(account_id)
	# df_games.to_csv('temp_matchlist.csv')
	# df_games = pd.read_csv('temp_matchlist.csv', index_col=0)

	total_games = len(df_games)
	print('total games:', total_games)
	df_games = determine_games_to_collect(df_games)
	games_to_collect = len(df_games)
	print('games currently in database:', total_games - games_to_collect)
	print('games to collect:', len(df_games))

	if df_games.empty:
		df_games = pd.DataFrame(columns=['game_id', 'queue', 'duration', 'winner', 'forfeit', 'duration'])
		df_games.set_index('game_id', inplace=True)
		df_players = pd.DataFrame(columns=['game_id', 'player_id', 'champion_id', 'win'])
		df_remakes = pd.DataFrame(columns=['game_id', 'queue', 'duration', 'winner', 'forfeit', 'duration'])
		df_remakes.set_index('game_id', inplace=True)
		return  df_games, df_players, df_remakes

	df_m = riot_api.get_matches(df_games)
	blue_win = lambda x: x[0]['win'] == 'Win'
	df_games['winner'] = np.where(df_m.teams.apply(blue_win), 100, 200)
	df_games['duration'] = df_m.gameDuration
	df_games['forfeit'] = riot_api.get_forfeits(df_games)

	# filter out remakes--this is hidden but important
	df_games, df_remakes = riot_api.filter_remakes(df_games)
	df_m, _ = riot_api.filter_remakes(df_m)
	print('valid games:', len(df_games))
	print('remakes:', len(df_remakes))

	extract_player_id = lambda x, i: x[i]['player']['accountId']
	extract_champion_id = lambda x, i: x[i]['championId']
	extract_team = lambda x, i: x[i]['teamId']

	player_ids = []
	champion_ids = []
	wins = []
	game_ids = []
	# 10 players per game is hardcoded here
	for i in range(10):
		player_ids.extend(list(df_m.participantIdentities.apply(extract_player_id, args=(i,))))
		champion_ids.extend(list(df_m.participants.apply(extract_champion_id, args=(i,))))
		wins.extend(list((df_m.participants.apply(extract_team, args=(i,)) == df_games.winner).apply(int)))
		game_ids.extend(list(df_m.index))

	df_players = pd.DataFrame({'game_id': game_ids, 'player_id': player_ids, 'champion_id': champion_ids, 'win': wins})

	# df_players.to_csv('df_players.csv')
	# df_games.to_csv('df_games.csv')
	# print('df_games')
	# print(df_games)
	# print('df_players')
	# print(df_players)
	# print('df_remakes')
	# print(df_remakes)

	return df_games, df_players, df_remakes


def determine_games_to_collect(df_games):
	'''
	collects games from matchlist already in games table and stores in temporary preexisting_games table
	returns df consisting of games that still need to be downloaded from api
	'''
	db = get_db()
	pd.Series(data=df_games.index, name='game_id').to_sql('matchlist', db, if_exists='append', index=False)
	db.execute('''
				INSERT INTO preexisting_games(game_id, queue, duration, winner, forfeit, creation)
				SELECT g.game_id, g.queue, g.duration, g.winner, g.forfeit, g.creation
				FROM games g INNER JOIN matchlist m ON g.game_id = m.game_id
				''')
	db.execute('''
				INSERT INTO preexisting_players(game_id, player_id, champion_id, win)
				SELECT p.game_id, p.player_id, p.champion_id, p.win
				FROM players p INNER JOIN matchlist m ON p.game_id = m.game_id
				''')
	new_games_ids = pd.read_sql('''
								SELECT m.game_id
								FROM matchlist m LEFT OUTER JOIN preexisting_games pg ON pg.game_id = m.game_id
								WHERE pg.game_id IS NULL
								''', con=db)
	df_games = pd.merge(df_games, new_games_ids, left_index=True, right_on='game_id').set_index('game_id')
	return df_games


def create_temporary_tables():
	'''
	creates two temporaray tables for the current player: matchlist, preexisting_games, new_games
	matchlist is a single-column table containing game_ids played by the player
	preexisting_games are games already present in the sqlite database
	new_games are games to be downloaded from riot's api
	'''
	db = get_db()
	db.execute(''' CREATE TEMP TABLE matchlist(game_id INTEGER PRIMARY KEY)''')
	db.execute('''
				CREATE TEMP TABLE preexisting_games(
					game_id INTEGER PRIMARY KEY,
					queue INTEGER NOT NULL,
					duration INTEGER NOT NULL,
					winner INTEGER NOT NULL,
					forfeit INTEGER NOT NULL,
					creation INTEGER NOT NULL)
				''')
	db.execute('''
				CREATE TEMP TABLE new_games(
					game_id INTEGER PRIMARY KEY,
					queue INTEGER NOT NULL,
					duration INTEGER NOT NULL,
					winner INTEGER NOT NULL,
					forfeit INTEGER NOT NULL,
					creation INTEGER NOT NULL)
				''')
	db.execute('''
				CREATE TEMP TABLE preexisting_players(
				game_id INTEGER NOT NULL,
				player_id TEXT NOT NULL,
				champion_id INTEGER NOT NULL,
				win INTEGER NOT NULL,
				PRIMARY KEY (game_id, player_id))
				''')
	db.execute('''
				CREATE TEMP TABLE new_players(
				game_id INTEGER NOT NULL,
				player_id TEXT NOT NULL,
				champion_id INTEGER NOT NULL,
				win INTEGER NOT NULL,
				PRIMARY KEY (game_id, player_id))
				''')

def drop_temporary_tables():
	''' drops the temporary tables created in create_temporary_tables '''
	db = get_db()
	db.execute('DROP TABLE matchlist')
	db.execute('DROP TABLE preexisting_games')
	db.execute('DROP TABLE new_games')
	db.execute('DROP TABLE preexisting_players')
	db.execute('DROP TABLE new_players')