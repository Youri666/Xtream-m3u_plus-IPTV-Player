"""Normalize provider episode collections without guessing season numbers."""


def episodes_by_season(episodes):
    """Accept season mappings or episode lists with explicit season metadata."""
    if isinstance(episodes, dict):
        if not all(isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
                   for rows in episodes.values()):
            raise ValueError('Invalid episode collection')
        return {str(season): rows for season, rows in episodes.items() if rows}
    if isinstance(episodes, list):
        # JSON arrays can encode consecutive season groups as nested lists.
        if episodes and all(isinstance(group, list) for group in episodes):
            episodes = [episode for group in episodes for episode in group]
        seasons = {}
        for episode in episodes:
            if not isinstance(episode, dict):
                raise ValueError('Invalid episode entry')
            season = episode.get('season')
            if season is None or str(season).strip() == '':
                raise ValueError('Episode has no season metadata')
            seasons.setdefault(str(season), []).append(episode)
        return seasons
    raise ValueError('Invalid episode collection type')
