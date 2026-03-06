#!/usr/bin/env python3
"""
Signal Attribution - Track signal-to-outcome accuracy

Analyzes closed trades to calculate signal accuracy metrics including per-bot performance
and per-factor success rates. Generates attribution scores for continuous improvement.

Usage:
    python3 signal_attribution.py --supabase-url URL --supabase-key KEY
    python3 signal_attribution.py  # Uses credentials from .env

Output:
    Creates signal_scores.json with per-bot and per-factor statistics
"""

import argparse
import json
import os
import sys
import requests
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv


class SignalAttribution:
    """Signal attribution and performance tracking engine."""
    
    def __init__(self, supabase_url: str, supabase_key: str):
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.headers = {
            'apikey': supabase_key,
            'Authorization': f'Bearer {supabase_key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        
    def fetch_closed_trades(self) -> List[Dict[str, Any]]:
        """Fetch all closed trades from Supabase."""
        try:
            # Query for closed trades (status = 'closed')
            url = f"{self.supabase_url}/rest/v1/trades"
            params = {
                'status': 'eq.closed',
                'select': '*',
                'order': 'created_at.desc'
            }
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            trades = response.json()
            print(f"Fetched {len(trades)} closed trades from database", file=sys.stderr)
            return trades
            
        except requests.RequestException as e:
            print(f"Failed to fetch trades from Supabase: {str(e)}", file=sys.stderr)
            return []
        except Exception as e:
            print(f"Error processing trades: {str(e)}", file=sys.stderr)
            return []
    
    def parse_trade_outcome(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Parse trade outcome and metrics."""
        try:
            # Calculate basic metrics
            entry_price = float(trade.get('entry_price', 0))
            exit_price = float(trade.get('exit_price', 0))
            quantity = float(trade.get('quantity', 0))
            side = trade.get('side', '').lower()
            
            if entry_price == 0 or exit_price == 0:
                return {'is_valid': False}
                
            # Calculate return
            if side == 'long':
                pnl = (exit_price - entry_price) * quantity
                return_pct = ((exit_price - entry_price) / entry_price) * 100
            else:  # short
                pnl = (entry_price - exit_price) * quantity  
                return_pct = ((entry_price - exit_price) / entry_price) * 100
                
            # Calculate hold time
            entry_time = trade.get('created_at')
            exit_time = trade.get('closed_at')
            hold_hours = 0
            
            if entry_time and exit_time:
                try:
                    entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
                    exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00'))
                    hold_hours = (exit_dt - entry_dt).total_seconds() / 3600
                except:
                    hold_hours = 0
            
            return {
                'is_valid': True,
                'is_winner': pnl > 0,
                'pnl': pnl,
                'return_pct': return_pct,
                'hold_hours': hold_hours,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'quantity': quantity,
                'side': side
            }
            
        except Exception as e:
            print(f"Error parsing trade outcome: {str(e)}", file=sys.stderr)
            return {'is_valid': False}
    
    def calculate_bot_stats(self, trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Calculate performance statistics per bot/signal source."""
        bot_stats = {}
        
        for trade in trades:
            signal_source = trade.get('signal_source', 'unknown')
            outcome = self.parse_trade_outcome(trade)
            
            if not outcome.get('is_valid'):
                continue
                
            if signal_source not in bot_stats:
                bot_stats[signal_source] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_pnl': 0.0,
                    'total_return_pct': 0.0,
                    'total_hold_hours': 0.0,
                    'gross_wins': 0.0,
                    'gross_losses': 0.0,
                    'trade_details': []
                }
            
            stats = bot_stats[signal_source]
            stats['total_trades'] += 1
            stats['total_pnl'] += outcome['pnl']
            stats['total_return_pct'] += outcome['return_pct']
            stats['total_hold_hours'] += outcome['hold_hours']
            
            if outcome['is_winner']:
                stats['winning_trades'] += 1
                stats['gross_wins'] += abs(outcome['pnl'])
            else:
                stats['losing_trades'] += 1
                stats['gross_losses'] += abs(outcome['pnl'])
                
            stats['trade_details'].append({
                'ticker': trade.get('ticker'),
                'side': outcome['side'],
                'return_pct': outcome['return_pct'],
                'hold_hours': outcome['hold_hours'],
                'date': trade.get('created_at', '')[:10]  # Just the date
            })
        
        # Calculate derived metrics
        for signal_source, stats in bot_stats.items():
            total = stats['total_trades']
            if total > 0:
                stats['win_rate_pct'] = (stats['winning_trades'] / total) * 100
                stats['avg_return_pct'] = stats['total_return_pct'] / total
                stats['avg_hold_hours'] = stats['total_hold_hours'] / total
                
                # Profit factor = gross wins / gross losses
                if stats['gross_losses'] > 0:
                    stats['profit_factor'] = stats['gross_wins'] / stats['gross_losses']
                else:
                    stats['profit_factor'] = float('inf') if stats['gross_wins'] > 0 else 0
                    
                # Expectancy per trade
                stats['expectancy'] = stats['total_pnl'] / total
                
                # Clean up - remove trade details for final output (too verbose)
                del stats['trade_details']
            
        return bot_stats
    
    def parse_trade_factors(self, trade: Dict[str, Any]) -> List[str]:
        """Extract factors from trade record."""
        factors = []
        
        # Try to parse factors field (could be JSON string or list)
        factors_data = trade.get('factors')
        if factors_data:
            try:
                if isinstance(factors_data, str):
                    parsed = json.loads(factors_data)
                else:
                    parsed = factors_data
                    
                # Handle different factor formats
                if isinstance(parsed, list):
                    factors.extend(parsed)
                elif isinstance(parsed, dict):
                    # If it's a dict, use keys as factor names
                    factors.extend(parsed.keys())
                    # Also look for high-scoring factors
                    for key, value in parsed.items():
                        try:
                            if isinstance(value, (int, float)) and value > 0.7:
                                factors.append(f"{key}_strong")
                        except:
                            pass
                            
            except json.JSONDecodeError:
                # If factors is a simple string, split it
                if isinstance(factors_data, str):
                    factors.extend([f.strip() for f in factors_data.split(',') if f.strip()])
        
        # Also look for other factor-related fields
        for field in ['entry_reason', 'signal_type', 'strategy']:
            value = trade.get(field)
            if value and isinstance(value, str):
                factors.append(f"{field}_{value}")
        
        return list(set(factors))  # Remove duplicates
    
    def calculate_factor_stats(self, trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Calculate success rates per factor."""
        factor_stats = {}
        
        for trade in trades:
            outcome = self.parse_trade_outcome(trade)
            if not outcome.get('is_valid'):
                continue
                
            factors = self.parse_trade_factors(trade)
            
            for factor in factors:
                if factor not in factor_stats:
                    factor_stats[factor] = {
                        'total_trades': 0,
                        'winning_trades': 0,
                        'total_return_pct': 0.0
                    }
                
                stats = factor_stats[factor]
                stats['total_trades'] += 1
                stats['total_return_pct'] += outcome['return_pct']
                
                if outcome['is_winner']:
                    stats['winning_trades'] += 1
        
        # Calculate derived metrics
        for factor, stats in factor_stats.items():
            total = stats['total_trades']
            if total > 0:
                stats['win_rate_pct'] = (stats['winning_trades'] / total) * 100
                stats['avg_return_pct'] = stats['total_return_pct'] / total
                
                # Factor strength score (combines win rate and return)
                # Score = win_rate * avg_return, normalized
                stats['strength_score'] = (stats['win_rate_pct'] / 100) * abs(stats['avg_return_pct'])
        
        return factor_stats
    
    def generate_signal_scores(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comprehensive signal attribution report."""
        bot_stats = self.calculate_bot_stats(trades)
        factor_stats = self.calculate_factor_stats(trades)
        
        # Summary statistics
        total_trades = len([t for t in trades if self.parse_trade_outcome(t).get('is_valid')])
        total_winners = len([t for t in trades if self.parse_trade_outcome(t).get('is_winner')])
        overall_win_rate = (total_winners / total_trades * 100) if total_trades > 0 else 0
        
        # Sort bots by profit factor
        sorted_bots = sorted(
            bot_stats.items(), 
            key=lambda x: x[1].get('profit_factor', 0), 
            reverse=True
        )
        
        # Sort factors by strength score
        sorted_factors = sorted(
            [(k, v) for k, v in factor_stats.items() if v['total_trades'] >= 3],
            key=lambda x: x[1].get('strength_score', 0),
            reverse=True
        )
        
        return {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'summary': {
                'total_analyzed_trades': total_trades,
                'overall_win_rate_pct': round(overall_win_rate, 2),
                'total_bots': len(bot_stats),
                'total_factors': len(factor_stats)
            },
            'bot_performance': {
                'ranked': dict(sorted_bots),
                'all': bot_stats
            },
            'factor_analysis': {
                'top_factors': dict(sorted_factors[:20]),  # Top 20 factors
                'all': factor_stats
            }
        }
    
    def run(self) -> bool:
        """Run signal attribution analysis."""
        print("Starting signal attribution analysis...", file=sys.stderr)
        
        # Fetch trades
        trades = self.fetch_closed_trades()
        if not trades:
            print("No trades found or failed to fetch trades", file=sys.stderr)
            return False
        
        # Generate signal scores
        signal_scores = self.generate_signal_scores(trades)
        
        # Write output file
        try:
            output_path = 'signal_scores.json'
            with open(output_path, 'w') as f:
                json.dump(signal_scores, f, indent=2)
            
            print(f"Signal attribution analysis complete. Results written to {output_path}", file=sys.stderr)
            
            # Print summary to stdout
            summary = signal_scores['summary']
            print(f"Analyzed {summary['total_analyzed_trades']} trades from {summary['total_bots']} bots")
            print(f"Overall win rate: {summary['overall_win_rate_pct']:.1f}%")
            
            # Print top performing bot
            if signal_scores['bot_performance']['ranked']:
                top_bot = list(signal_scores['bot_performance']['ranked'].items())[0]
                print(f"Top performer: {top_bot[0]} (PF: {top_bot[1].get('profit_factor', 0):.2f})")
            
            return True
            
        except Exception as e:
            print(f"Failed to write signal scores: {str(e)}", file=sys.stderr)
            return False


def load_env_credentials() -> tuple:
    """Load Supabase credentials from .env file."""
    # Try to load from workspace root
    env_path = '/Users/markmatuska/.openclaw/workspace/.env'
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()  # Load from current directory
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_ANON_KEY')
    
    return supabase_url, supabase_key


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description='Signal attribution and performance tracking')
    parser.add_argument('--supabase-url', help='Supabase URL (or set SUPABASE_URL in .env)')
    parser.add_argument('--supabase-key', help='Supabase anon key (or set SUPABASE_KEY in .env)')
    
    args = parser.parse_args()
    
    # Get credentials from args or environment
    supabase_url = args.supabase_url
    supabase_key = args.supabase_key
    
    if not supabase_url or not supabase_key:
        env_url, env_key = load_env_credentials()
        supabase_url = supabase_url or env_url
        supabase_key = supabase_key or env_key
    
    if not supabase_url or not supabase_key:
        print("Error: Supabase credentials required. Provide via --supabase-url/--supabase-key or set SUPABASE_URL/SUPABASE_KEY in .env", file=sys.stderr)
        sys.exit(1)
    
    try:
        analyzer = SignalAttribution(supabase_url, supabase_key)
        success = analyzer.run()
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"Signal attribution failed: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()