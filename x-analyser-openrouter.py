import tweepy
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress

class TwitterChatAnalyser:
    def __init__(self):
        self.console = Console()
        self.tweets = []
        self.username = None
        self.cache_dir = Path(__file__).parent / 'cache'
        self.cache_dir.mkdir(exist_ok=True)
        self.setup_clients()

    def setup_clients(self):
        script_dir = Path(__file__).parent
        keys_dir = script_dir.parent / 'keys'
        
        try:
            with open(keys_dir / '../../keys/x-token.txt') as f:
                self.twitter_client = tweepy.Client(bearer_token=f.read().strip())
            with open(keys_dir / '../../keys/key-openrouter.txt') as f:
                self.openrouter_key = f.read().strip()
        except FileNotFoundError:
            self.console.print("[red]Error: API key files not found in ../../keys/[/red]")
            exit(1)

    def load_cached_tweets(self, username):
        cache_file = self.cache_dir / f"{username}_tweets.json"
        if not cache_file.exists():
            return None, None
            
        with open(cache_file) as f:
            data = json.load(f)
            cache_time = datetime.fromisoformat(data['cached_at'])
            
        if datetime.now() - cache_time > timedelta(hours=24):
            return None, None
            
        return data['tweets'], cache_time

    def save_tweets_to_cache(self, username, tweets):
        cache_data = {
            'tweets': tweets,
            'cached_at': datetime.now().isoformat()
        }
        
        cache_file = self.cache_dir / f"{username}_tweets.json"
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)

    def fetch_tweets(self, username):
        with Progress() as progress:
            task = progress.add_task("[cyan]Checking cache...", total=100)
            
            cached_tweets, cache_time = self.load_cached_tweets(username)
            if cached_tweets:
                self.tweets = cached_tweets
                progress.update(task, completed=100)
                self.console.print(f"[green]Using cached tweets from {cache_time.strftime('%Y-%m-%d %H:%M:%S')}[/green]")
                return True
                
            progress.update(task, description="[cyan]Fetching fresh tweets...", completed=30)
            
            try:
                user = self.twitter_client.get_user(username=username)
                progress.update(task, advance=20)
                
                if not user.data:
                    return False
                    
                tweets = self.twitter_client.get_users_tweets(
                    id=user.data.id,
                    max_results=10,
                    tweet_fields=['created_at', 'public_metrics'],
                    exclude=['retweets', 'replies']
                )
                
                if tweets.data:
                    self.tweets = [{
                        'id': t.id,
                        'text': t.text,
                        'created_at': t.created_at.isoformat(),
                        'metrics': t.public_metrics
                    } for t in tweets.data]
                    
                    self.save_tweets_to_cache(username, self.tweets)
                    progress.update(task, completed=100)
                    return True
                    
            except Exception as e:
                self.console.print(f"[red]Error: {str(e)}[/red]")
                return False
        return False

    def analyse_with_openrouter(self, question, model="anthropic/claude-3-sonnet"):
        if not self.tweets:
            self.console.print("[yellow]No tweets loaded.[/yellow]")
            return
            
        with Progress() as progress:
            task = progress.add_task("[cyan]Analysing...", total=100)
            
            messages = [
                {
                    "role": "system",
                    "content": "You are analyzing Twitter/X user activity. Focus on key patterns in behavior, interests, and communication style. Provide concise, data-driven insights based only on the provided tweets."
                },
                {
                    "role": "user", 
                    "content": f"Based on these tweets from @{self.username}, {question}\n\nTweets:\n{json.dumps(self.tweets, indent=2)}"
                }
            ]
            
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openrouter_key}",
                        "HTTP-Referer": "https://github.com/your-repo", # Required by OpenRouter
                        "X-Title": "Twitter Analyzer",  # Required by OpenRouter
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 1000
                    }
                )
                progress.update(task, advance=100)
                
                if response.status_code == 200:
                    analysis = response.json()['choices'][0]['message']['content']
                    self.console.print(Panel(
                        Markdown(analysis),
                        title="Analysis",
                        border_style="cyan"
                    ))
                else:
                    self.console.print(f"[red]Error {response.status_code}: {response.text}[/red]")
                    
            except Exception as e:
                self.console.print(f"[red]Error: {str(e)}[/red]")

    def start_chat(self):
        self.console.clear()
        self.console.print("[bold cyan]Twitter Analysis Chat[/bold cyan]")
        
        username = Prompt.ask("Enter Twitter handle").strip('@')
        self.console.print(f"\nChecking tweets for [bold]@{username}[/bold]")
        
        if self.fetch_tweets(username):
            self.console.print(f"[green]Loaded {len(self.tweets)} tweets[/green]")
            self.username = username
            self.chat_loop()
        else:
            self.console.print("[red]Failed to fetch tweets[/red]")

    def chat_loop(self):
        self.console.print("\n[cyan]Ask any questions about these tweets (or type 'quit' to exit)[/cyan]")
        
        while True:
            question = Prompt.ask("\nWhat would you like to know?")
            
            if question.lower() == 'quit':
                break
            else:
                self.analyse_with_openrouter(question)

def main():
    analyser = TwitterChatAnalyser()
    analyser.start_chat()

if __name__ == '__main__':
    main()