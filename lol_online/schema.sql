DROP TABLE IF EXISTS games;
DROP TABLE IF EXISTS players;

CREATE TABLE games (
	game_id INTEGER PRIMARY KEY,
	queue INTEGER NOT NULL,
	duration INTEGER NOT NULL,
	winner INTEGER NOT NULL, -- (100 = blue, 200 = red)
	forfeit INTEGER NOT NULL,
	creation INTEGER NOT NULL
);

CREATE TABLE players (
	game_id INTEGER NOT NULL,
	player_id TEXT NOT NULL,
	champion_id INTEGER NOT NULL,
	win INTEGER NOT NULL, 
	PRIMARY KEY (game_id, player_id)
);