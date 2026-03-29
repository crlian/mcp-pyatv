from pyatv.const import RepeatState, ShuffleState


def format_playing(playing) -> dict:
    result = {
        "title": playing.title,
        "artist": playing.artist,
        "album": playing.album,
        "genre": playing.genre,
        "media_type": playing.media_type.name if playing.media_type else None,
        "state": playing.device_state.name if playing.device_state else None,
        "position": playing.position,
        "total_time": playing.total_time,
        "shuffle": playing.shuffle.name if playing.shuffle else None,
        "repeat": playing.repeat.name if playing.repeat else None,
    }
    if playing.series_name:
        result["series_name"] = playing.series_name
    if playing.season_number is not None:
        result["season_number"] = playing.season_number
    if playing.episode_number is not None:
        result["episode_number"] = playing.episode_number
    return result


def format_device(config) -> dict:
    services = []
    for service in config.services:
        services.append(
            {
                "protocol": service.protocol.name,
                "port": service.port,
                "paired": service.credentials is not None,
            }
        )
    di = config.device_info
    return {
        "name": config.name,
        "identifier": config.identifier,
        "address": str(config.address),
        "model": str(di.model) if di else None,
        "model_str": di.model_str if di else None,
        "raw_model": di.raw_model if di else None,
        "os_version": str(di.version) if di else None,
        "services": services,
    }


def parse_shuffle(state: str) -> ShuffleState:
    mapping = {
        "off": ShuffleState.Off,
        "songs": ShuffleState.Songs,
        "albums": ShuffleState.Albums,
    }
    if state.lower() not in mapping:
        raise ValueError(f"Invalid shuffle state: {state}. Use: off, songs, albums")
    return mapping[state.lower()]


def parse_repeat(state: str) -> RepeatState:
    mapping = {
        "off": RepeatState.Off,
        "track": RepeatState.Track,
        "all": RepeatState.All,
    }
    if state.lower() not in mapping:
        raise ValueError(f"Invalid repeat state: {state}. Use: off, track, all")
    return mapping[state.lower()]
