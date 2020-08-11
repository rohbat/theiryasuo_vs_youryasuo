import time
from collections import Counter
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import sys

from riotwatcher import LolWatcher, ApiError

from champions_dict import *


# global
API_KEY = 'get_an_api_key_from_riots_website'
REGION = 'na1'


def get_matchlist(watcher, account_id, region=REGION):
	''' retrieves list of all matches for the given account id and returns as a dataframe '''
	matches = []
	i = 0

	while True:
		try:
			match = watcher.match.matchlist_by_account(region, account_id, begin_index=100*i, end_index=100*(i+1)) # could potentially limit to desired game modes here~~
			if match['matches']:
				matches.append(match)
				i += 1
				time.sleep(.1)
				print(i*100, '/ ?')
			else:
				break
		except:
			pass

	all_matches = [m for match in matches for m in match['matches']]
	df_ml = pd.DataFrame(all_matches)
	df_ml.index = df_ml.gameId
	df_ml.index.rename('game_id', inplace=True)
	df_ml.drop('gameId', axis=1, inplace=True)
	df_ml.sort_index(inplace=True)
	return df_ml


def get_all_matches(watcher, matchlist, region=REGION):
	''' retrieves detailed reports of all matches in the given matchlist and returns as a dataframe '''
	matches = []
	failed = []

	for i, match in enumerate(matchlist):
		try:
			matches.append(watcher.match.by_id(region, match))
		except:
			failed.append(match)
		if not i % 100:
			print(i, '/', len(matchlist))
		time.sleep(1.5)
	print(len(matchlist), '/', len(matchlist))

	print('Number failed:', len(failed))
	
	if failed:
		print('Retrying...')
		ffailed = []

		for match in failed:
			try:
				matches.append(watcher.match.by_id(region, match))
			except:
				ffailed.append(match)
			time.sleep(1.5)

		if ffailed:
			print('Doubly failed match ids:')
			print(ffailed)
		else:
			print('Success')

	df = pd.DataFrame(matches)
	df.index = df.gameId
	df.index.rename('game_id', inplace=True)
	df.drop('gameId', axis=1, inplace=True)
	df.sort_index(inplace=True)
	return df


def get_all_timelines(watcher, matchlist, region=REGION):
	''' retrieves detailed reports of all match timelines in the given matchlist and returns as a dataframe '''
	timelines = []
	game_id = []
	failed = []

	for i, match in enumerate(matchlist):
		try:
			timelines.append(watcher.match.timeline_by_match(region, match))
			game_id.append(match)
		except:
			failed.append(match)
		if not i % 10:
			print(i, '/', len(matchlist))
		time.sleep(1.5)
	print(len(matchlist), '/', len(matchlist))

	print('Number failed:', len(failed))

	if failed:
		print('Retrying...')
		ffailed = []

		for match in failed:
			try:
				timelines.append(watcher.match.timeline_by_match(region, match))
				game_id.append(match)
			except:
				ffailed.append(match)
			time.sleep(1.5)

		if ffailed:
			print('Doubly failed match ids:')
			print(ffailed)
		else:
			print('Success')

	df_tl = pd.DataFrame(timelines, index=game_id)
	df_tl.index.rename('game_id', inplace=True)
	df_tl.sort_index(inplace=True)
	return df_tl


def filter_by_queue(df, queue='sr'):
	'''
	MOST RELEVANT 5V5 QUEUE TYPES FROM RIOT API:
	400: summoners rift, normal draft
	420: summoners rift, ranked solo
	430: summoners rift, normal blind pick
	440: summoners rift, ranked flex
	450: aram
	700: summoners rift, clash

	valid queue codes: sr, ranked, soloq, clash, aram
	with included queue types below
	'''

	# there's probably a more flexible way to do this, but this is easy and quick
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	valid_queue_ids = {
		'sr': [400, 420, 430, 440, 700],
		'ranked': [420, 440],
		'soloq': 420,
		'clash': 700,
		'aram': 450,
		'sr_and_aram': [400, 420, 430, 440, 450, 700],
	}
	if type(valid_queue_ids[queue]) is int:
		filtered_df = df[df.queueId == valid_queue_ids[queue]]
	else:
		queue_mask = df.queueId.apply(lambda x: x in valid_queue_ids[queue])
		filtered_df = df[queue_mask]

	return filtered_df
	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def match_details(matches, account_id, queue='sr'):
	''' returns dataframe consisting of important details for all matches played in the desired queue '''
	filtered_matches = filter_by_queue(matches, queue)
	match_details = []
	for i in range(len(filtered_matches)):
		details = extract_details_from_match(filtered_matches.iloc[i,:], account_id)
		if details:
			match_details.append(details)

	df = pd.DataFrame(match_details)
	df.index = df.game_id
	df.drop('game_id', axis=1, inplace=True)
	return df


def extract_details_from_match(match, account_id):
	''' returns dictionary containing stats about the match from the perspective of account_name '''
	duration = match['gameDuration']
	if duration < 500: # ensure that the match is not a remake
		return None

	# finds player by player id--champion played is also present in df_ml but I don't think getting from there is any faster
	for p in match.participantIdentities:
		if p['player']['accountId'] == account_id:
			player_participant_id = p['participantId']
			break

	for p in match['participants']:
		if p['participantId'] == player_participant_id:
			win = p['stats']['win']
			blue_side = (p['teamId'] == 100) # 100 is blue side, 200 is red
			player_champion = p['championId']

	game_detail = {
		'game_id': match.name,
		'win': win,
		'duration': duration,
		'blue_side': blue_side,
		'player_champion': player_champion,
		'ally_champions': [],
		'enemy_champions': [],
	}

	for p in match['participants']:
		if p['stats']['win'] != win:
			game_detail['enemy_champions'].append(p['championId'])
		elif p['participantId'] != player_participant_id:
			game_detail['ally_champions'].append(p['championId'])

	return game_detail


def wr_by_player_champ(games):
	''' returns a dataframe containing games, wins, losses, winrate and p_value (two-tailed) for champions played by account_name '''
	pc_group = games.groupby('player_champion')

	wr = pd.concat([pc_group.win.count(), pc_group.win.sum().astype(int)], axis=1).fillna(0)
	wr.columns = ['games', 'wins']
	wr.index = wr.index.map(id_to_champ)

	wr['losses'] = wr.games - wr.wins
	wr['winrate'] = wr.wins / wr.games

	p_value = lambda champ: stats.binom_test(champ.wins, champ.games) # p = 0.5
	wr['p_value'] = wr.apply(p_value, axis=1)

	return wr.sort_values(by='winrate', ascending=False)


def wr_by_team_champs(games, team):
	'''
	returns a dataframe containing games, wins, losses, winrates and p_value (two-tailed) for champions on the given team
	from perspective of account_name
	team = enemy: stats AGAINST champs on enemy team
	team = ally: stats WITH champs on team

	'''
	team_champions = team + '_champions'
	win = []
	lose = []

	for champs in games[games.win][team_champions]:
		win.extend(champs)
	for champs in games[~games.win][team_champions]:
		lose.extend(champs)

	win = Counter(win)
	lose = Counter(lose)

	wr = pd.DataFrame([win, lose]).T.sort_index().fillna(0)
	wr.columns = ['wins', 'losses']
	wr.index = wr.index.map(id_to_champ)
	wr['games'] = wr.wins + wr.losses
	wr['winrate'] = wr.wins / wr.games
	wr = wr[['games', 'wins', 'losses', 'winrate']]

	p_value = lambda champ: stats.binom_test(champ.wins, champ.games) # p = 0.5
	wr['p_value'] = wr.apply(p_value, axis=1)

	return wr.sort_values(by='winrate', ascending=False)


def oldest_recorded_match(matches):
	''' returns the timestamp of the oldest recorded match '''
	if type(matches.iloc[0].timestamp) == int: # if gotten from api
		return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(matches.iloc[0].timestamp))
	else:
		return matches.iloc[0].timestamp


def unplayed_champions(games):
	'''	returns list of champions that have never been played in the previously determined queue type '''
	return sorted(list(set(champ_to_id_dict.keys() - set(games.player_champion.map(id_to_champ).unique()))))


def their_yasuo_vs_your_yasuo(ally, enemy):
	'''
	combines tables of ally and enemy champions games and winrates
	adds delta_winrate column that descibes how much more a given champion wins when on
		the other team (FROM THEIR PERSPECTIVE) than when on your team (FROM YOURS)
	a high negative value indicates that that champ performs  better when against you
	a high positive value indicates that that champ performs better when on your team
	'''
	wr = pd.DataFrame([ally.games, ally.winrate, enemy.games, enemy.winrate]).T
	wr.columns = ['games_with', 'winrate_with', 'games_against', 'winrate_against']
	wr['delta_winrate'] = wr.winrate_with - (1 - wr.winrate_against)

	return wr.sort_values(by='delta_winrate')


def blue_red_winrates(games):
	'''
	outputs overall, blue- and red-side winrates
	compare: https://www.leagueofgraphs.com/rankings/blue-vs-red
	'''
	ow = games.win.sum()
	og = games.win.count()
	print('Overall winrate: {} wins / {} games ({:.3f}%)'.format(ow, og, ow/og*100))

	blue = games[games.blue_side]
	bw = blue.win.sum()
	bg = blue.win.count()
	print('Blue side winrate: {} wins / {} games ({:.3f}%)'.format(bw, bg, bw/bg*100))

	red = games[~games.blue_side]
	rw = red.win.sum()
	rg = red.win.count()
	print('Red side winrate: {} wins / {} games ({:.3f}%)'.format(rw, rg, rw/rg*100), '\n')


def game_durations(games, forfeit=None):
	'''
	prints and plots stats for game durations
	can customize output for all (forfeit=None), forfeit (forfeit=True) or non-forfeit (forfeit=False) games
	compare: https://www.leagueofgraphs.com/rankings/game-durations
	'''
	win = games[games.win]
	loss = games[~games.win]
	all_mean = games.duration.mean()
	win_mean = win.duration.mean()
	loss_mean = loss.duration.mean()
	if forfeit == None:
		print('For all games:')
	elif forfeit == True:
		print('For games (probably) ended in forfeit:')
	else:
		print('For games (probably) not ended in forfeit:')
	print('Average game duration: {}:{:02d}'.format(int(all_mean/60), int(all_mean%60)))
	print('Winning game duration: {}:{:02d}'.format(int(win_mean/60), int(win_mean%60)))
	print('Losing game duration: {}:{:02d}'.format(int(loss_mean/60), int(loss_mean%60)), '\n')

	low_min = games.duration.min() // 60
	low_bin = low_min * 60
	high_min = games.duration.max() // 60
	high_bin = (high_min+1) * 60
	nbins = (high_min - low_min) + 2
	bins = np.linspace(low_bin, high_bin, nbins)

	all_cut = pd.cut(games.duration, bins=bins, right=False)
	win_cut = pd.cut(win.duration, bins=bins, right=False)
	loss_cut = pd.cut(loss.duration, bins=bins, right=False)

	plt.style.use('ggplot')
	win.groupby(win_cut).win.count().plot(label='wins')
	loss.groupby(loss_cut).win.count().plot(label='losses')

	low_tick = lambda x: (((x - 1) // 5) + 1) * 5
	high_tick = lambda x: ((x // 5) * 5) + 5
	low_bound = lambda x: -x % 5
	high_bound = lambda x: x - (x % 5) - 10

	plt.xticks(range(low_bound(low_min), high_bound(high_min), 5), range(low_tick(low_min), high_tick(high_min), 5)) # will break for games > 10 hours xD
	plt.xlabel('game duration (min)')
	plt.ylabel('count games')
	plt.legend()
	if forfeit == None:
		plt.title('game duration by win/loss (all games)')
	elif forfeit == True:
		plt.title('game duration by win/loss (forfeit games)')
	else:
		plt.title('game duration by win/loss (non-forfeit games)')
	plt.show()


def forfeit_game_durations(games, df_tl):
	'''
	segment games by probable forfeit status and call game durations to analyze and plot

	if the winning team wins without killing both opposing nexus turrets, assume the game was forfeit
	if the winning team kills both opposing nexus turrets before winning, assume the game was not forfeit

	the first case is always correct
	the second is generally correct, but if a team loses both nexus turrets before forfeiting, they are likely very close to losing 'naturally' anyway	
	this results in a (likely very slight) miscategorization of forfeit games as not forfeit
	'''
	blue_nexus_turrets_destroyed = []
	red_nexus_turrets_destroyed = []
	for game in df_tl.loc[games.index.values, 'frames']:
		# nexus turrets named by their x-coord--blue is 1748 and 2177--red is 12611 and 13052
		nexus_turrets = {1748: False, 2177: False, 12611: False, 13052: False}
		for frame in game:
			for event in frame['events']:
				if event['type'] == 'BUILDING_KILL' and event['towerType'] == 'NEXUS_TURRET':
					nexus_turrets[event['position']['x']] = True
		blue_nexus_turrets_destroyed.append(nexus_turrets[1748] and nexus_turrets[2177])
		red_nexus_turrets_destroyed.append(nexus_turrets[12611] and nexus_turrets[13052])
	blue_nexus_turrets_destroyed = pd.Series(blue_nexus_turrets_destroyed, index=games.index)
	red_nexus_turrets_destroyed = pd.Series(red_nexus_turrets_destroyed, index=games.index)

	forfeit_state = ~((red_nexus_turrets_destroyed & ~(games.win ^ games.blue_side)) | \
						(blue_nexus_turrets_destroyed & (games.win ^ games.blue_side)))

	game_durations(games[forfeit_state], forfeit=True)
	game_durations(games[~forfeit_state], forfeit=False)


def output_yas(yas):
	''' diplay yas and yas for yas '''
	print('Winrate differential by champion based on team:')
	print('a negative value indicates that a given champion performs better when on enemy team')
	print('a positive value indicates that a given champion performs better when on your team')
	print(yas, '\n')

	print('Is enemy team Yasuo actually better than your team Yasuo?')
	print(yas.loc['Yasuo'], '\n')


def output_winrates(wr_player, wr_ally, wr_enemy):
	''' display winrate dataframes '''
	print('Winrates by player champion:')
	print(wr_player, '\n')
	print('Winrates with allied champion:')
	print(wr_ally, '\n')
	print('Winrates against enemy champion:')
	print(wr_enemy, '\n')


def output_pvalues(wr_player, wr_ally, wr_enemy, threshold=0.05):
	''' display statistically significant p-values beyond given threshold '''
	threshold = 0.05
	print('Champion winrates with statistically significant p-values: p <', threshold, '\n')
	print('Player champions:')
	print(wr_player[wr_player.p_value < threshold].sort_values('p_value'), '\n')
	print('Allied champions:')
	print(wr_ally[wr_ally.p_value < threshold].sort_values('p_value'), '\n')
	print('Enemy champions:')
	print(wr_enemy[wr_enemy.p_value < threshold].sort_values('p_value'), '\n')


def get_from_api():
	''' retrieve datasets from riot '''
	print('Input account name:')
	account_name = input()

	watcher = LolWatcher(API_KEY)
	try:
		account = watcher.summoner.by_name(REGION, account_name)
	except ApiError as err:
		if err.response.status_code == 404:
			print('Invalid name. Try again:')
			account_name = input()
		else:
			print('Unknown error. Restart and try again.')
			quit()

	account_id = account['accountId']

	print('Account name (as input):', account_name) # various non-alphanumeric characters can be input but dont change the output
	print('Account name (Riot servers):', account['name']) # spaces and capitalization don't 'count' to distinguish names
	print('Account id:', account_id)

	print('Collecting matchlist')
	df_ml = get_matchlist(watcher, account_id, REGION)
	df_ml.to_json(account_name + '_matchlist.json')

	print('Collecting matches')
	df = get_all_matches(watcher, df_ml.index.values, REGION)
	df.to_json(account_name + '_allmatches.json')

	print('Collecting match timelines')
	df_tl = get_all_timelines(watcher, df_ml.index.values, REGION)
	df_tl.to_json(account_name + '_timelines.json')

	return account_id, account_name, df_ml, df, df_tl


def load_from_jsons():
	''' load datasets from json files '''
	account_name = 'vayneofcastamere'
	account_id = 'mFz2Q8FGiSdaVlWWMO4QB4VnE6R91oOTIh_Mr72iKsaUeQI'

	# if convert_axes isn't set to false, game ids are parsed as dates 
	df_ml = pd.read_json('vayneofcastamere_matchlist.json', convert_axes=False)
	df_ml.index = pd.to_numeric(df_ml.index)
	df_ml.index.rename('game_id', inplace=True)

	df = pd.read_json('vayneofcastamere_allmatches.json', convert_axes=False)
	df.index = pd.to_numeric(df.index)
	df.index.rename('game_id', inplace=True)

	df_tl = pd.read_json('vayneofcastamere_timelines.json', convert_axes=False)
	df_tl.index = pd.to_numeric(df_tl.index)
	df_tl.index.rename('game_id', inplace=True)

	print('Account name:', account_name)
	print('Account id:', account_id)
	return account_id, account_name, df_ml, df, df_tl


def show_all_features(source='load'):
	''' sample output of features included in file '''
	# LOAD FROM JSON
	if source == 'load':
		account_id, account_name, df_ml, df, df_tl = load_from_jsons()
	# RETRIEVE FROM RIOT
	elif source == 'api':
		account_id, account_name, df_ml, df, df_tl = get_from_api()

	games = match_details(df, account_id, queue='sr')

	# print(df_ml)
	# print(df)
	# print(df_tl)
	# print(games)

	print('Oldest match on record:', oldest_recorded_match(df_ml), '\n')
	print('You have never played the following champions in the given mode:\n', unplayed_champions(games), '\n')

	wr_player = wr_by_player_champ(games)
	wr_ally = wr_by_team_champs(games, 'ally')
	wr_enemy = wr_by_team_champs(games, 'enemy')
	yas = their_yasuo_vs_your_yasuo(wr_ally, wr_enemy)

	output_winrates(wr_player, wr_ally, wr_enemy)
	output_yas(yas)
	output_pvalues(wr_player, wr_ally, wr_enemy)

	blue_red_winrates(games)

	game_durations(games)
	forfeit_game_durations(games, df_tl)


def main():
	if len(sys.argv) == 1:
		source = 'load'
	else:
		source = sys.argv[1]
	show_all_features(source=source)

if __name__ == '__main__':
	main()
