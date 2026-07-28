import json
import os
import logging

logger = logging.getLogger('nano-trader-ai')

PERFORMANCE_PATH = os.path.join('data', 'state', 'performance.json')

_DEFAULT = {
    'wins': 0,
    'losses': 0,
    'total_win_pct': 0.0,
    'total_loss_pct': 0.0
}


def _load():
    if os.path.exists(PERFORMANCE_PATH):
        try:
            with open(PERFORMANCE_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for k, v in _DEFAULT.items():
                    data.setdefault(k, v)
                return data
        except Exception:
            pass
    return dict(_DEFAULT)


def _save(data):
    try:
        os.makedirs(os.path.dirname(PERFORMANCE_PATH), exist_ok=True)
        with open(PERFORMANCE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f'[PERF] Failed to save performance.json: {e}')


def record_win(profit_pct):
    data = _load()
    data['wins'] += 1
    data['total_win_pct'] += abs(profit_pct)
    _save(data)
    logger.info(f"[PERF] Win recorded: +{profit_pct*100:.2f}% | Total Wins: {data['wins']}")


def record_loss(loss_pct):
    data = _load()
    data['losses'] += 1
    data['total_loss_pct'] += abs(loss_pct)
    _save(data)
    logger.info(f"[PERF] Loss recorded: -{loss_pct*100:.2f}% | Total Losses: {data['losses']}")


def get_live_stats():
    data = _load()
    wins = data['wins']
    losses = data['losses']
    total = wins + losses
    if total < 10:
        return {'sufficient_data': False}
    win_rate = wins / total
    avg_win = data['total_win_pct'] / wins if wins > 0 else 0.0
    avg_loss = data['total_loss_pct'] / losses if losses > 0 else 0.001
    reward_risk = avg_win / avg_loss if avg_loss > 0 else 1.0
    return {
        'sufficient_data': True,
        'win_rate': round(win_rate, 4),
        'reward_risk_ratio': round(reward_risk, 4),
        'total_trades': total,
        'wins': wins,
        'losses': losses
    }
