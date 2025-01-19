import tweepy
import requests
import json
import base64
from datetime import datetime, timedelta
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress
import google.generativeai as genai
import PIL.Image
import os
os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'

class TwitterChatAnalyser:
    def __init__(self):
        self.console = Console()
        self.tweets = []
        self.username = None
        self.cache_dir = Path(__file__).parent / 'cache'
        self.media_dir = self.cache_dir / 'media'
        self.cache_dir.mkdir(exist_ok=True)
        self.media_dir.mkdir(exist_ok=True)
        self.setup_clients()

    def setup_clients(self):
        script_dir = Path(__file__).parent
        keys_dir = script_dir.parent / 'keys'
        
        try:
            # First check if GOOGLE_API_KEY is already set
            api_key = os.getenv('GOOGLE_API_KEY')
            if not api_key:
                # Try to read from file
                key_path = keys_dir / '../../keys/key-gemini.txt'
                self.console.print(f"Looking for API key at: {key_path.resolve()}")
                
                if not key_path.exists():
                    self.console.print("[red]Error: Gemini API key file not found[/red]")
                    exit(1)
                
                with open(key_path) as f:
                    api_key = f.read().strip()
                
                if not api_key:
                    self.console.print("[red]Error: Gemini API key file is empty[/red]")
                    exit(1)
                
                # Set the environment variable
                os.environ['GOOGLE_API_KEY'] = api_key
            
            # Configure Gemini
            genai.configure(api_key=api_key)
            genai.configure(transport="rest")
            
            # Initialize Twitter client
            with open(keys_dir / '../../keys/x-token.txt') as f:
                self.twitter_client = tweepy.Client(bearer_token=f.read().strip())
            
            # Initialize Gemini model
            self.model = genai.GenerativeModel('gemini-1.5-pro-latest',
                                             generation_config={
                                                 "max_output_tokens": 2048,
                                                 "temperature": 0.7,
                                                 "top_p": 0.8,
                                                 "top_k": 40
                                             })
            
            # Test the Gemini configuration
            try:
                test_response = self.model.generate_content("Test connection")
                self.console.print("[green]Successfully connected to Gemini API[/green]")
            except Exception as e:
                self.console.print(f"[red]Error testing Gemini connection: {str(e)}[/red]")
                raise
                
        except FileNotFoundError as e:
            self.console.print(f"[red]Error: Could not find key file: {str(e)}[/red]")
            exit(1)
        except Exception as e:
            self.console.print(f"[red]Error setting up clients: {str(e)}[/red]")
            exit(1)

    def clear_cache(self, username):
        """Clear cached tweets for a specific user"""
        cache_file = self.cache_dir / f"{username}_tweets.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
                # Also remove associated media files
                for tweet in self.tweets:
                    for media_path in tweet['media']:
                        try:
                            Path(media_path).unlink()
                        except:
                            pass
                self.console.print(f"[green]Cache cleared for @{username}[/green]")
                return True
            except Exception as e:
                self.console.print(f"[red]Error clearing cache: {str(e)}[/red]")
                return False
        return False

    def refresh_tweets(self):
        """Manually refresh tweets for current user"""
        if not self.username:
            self.console.print("[yellow]No user selected[/yellow]")
            return False
        
        self.console.print(f"[cyan]Refreshing tweets for @{self.username}...[/cyan]")
        self.clear_cache(self.username)
        return self.fetch_tweets(self.username, force_refresh=True)

    def load_cached_tweets(self, username):
        cache_file = self.cache_dir / f"{username}_tweets.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    cache_time = datetime.fromisoformat(data['timestamp'])
                    # Cache expires after 24 hours
                    if datetime.now() - cache_time < timedelta(hours=24):
                        return data['tweets'], cache_time
            except Exception as e:
                self.console.print(f"[yellow]Warning: Failed to load cache: {str(e)}[/yellow]")
        return None, None

    def save_tweets_to_cache(self, username, tweets):
        cache_file = self.cache_dir / f"{username}_tweets.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'tweets': tweets
                }, f)
        except Exception as e:
            self.console.print(f"[yellow]Warning: Failed to save cache: {str(e)}[/yellow]")

    def download_media(self, media_url, tweet_id):
        try:
            response = requests.get(media_url, timeout=10)
            if response.status_code == 200:
                media_path = self.media_dir / f"{tweet_id}.jpg"
                with open(media_path, 'wb') as f:
                    f.write(response.content)
                return str(media_path)
        except Exception as e:
            self.console.print(f"[yellow]Warning: Failed to download media: {str(e)}[/yellow]")
        return None

    def load_image(self, image_path):
        try:
            # Load image using PIL for better compatibility with Gemini
            img = PIL.Image.open(image_path)
            return img
        except Exception as e:
            self.console.print(f"[yellow]Warning: Failed to load image {image_path}: {str(e)}[/yellow]")
            return None

    def fetch_tweets(self, username, force_refresh=False):
        self.username = username
        with Progress() as progress:
            task = progress.add_task("[cyan]Checking cache...", total=100)
            
            if not force_refresh:
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
                    self.console.print("[red]User not found[/red]")
                    return False
                    
                tweets = self.twitter_client.get_users_tweets(
                    id=user.data.id,
                    max_results=10,
                    tweet_fields=['created_at', 'public_metrics', 'attachments'],
                    media_fields=['url', 'preview_image_url'],
                    expansions=['attachments.media_keys'],
                    exclude=['retweets', 'replies']
                )
                
                if tweets.data:
                    media_lookup = {m.media_key: m for m in (tweets.includes.get('media', []) or [])}
                    
                    self.tweets = []
                    for t in tweets.data:
                        tweet_data = {
                            'id': t.id,
                            'text': t.text,
                            'created_at': t.created_at.isoformat(),
                            'metrics': t.public_metrics,
                            'media': []
                        }
                        
                        if hasattr(t, 'attachments') and t.attachments:
                            media_keys = t.attachments.get('media_keys', [])
                            for key in media_keys:
                                media = media_lookup.get(key)
                                if media:
                                    media_url = media.url or media.preview_image_url
                                    if media_url:
                                        media_path = self.download_media(media_url, t.id)
                                        if media_path:
                                            tweet_data['media'].append(media_path)
                        
                        self.tweets.append(tweet_data)
                    
                    self.save_tweets_to_cache(username, self.tweets)
                    progress.update(task, completed=100)
                    return True
                    
            except Exception as e:
                self.console.print(f"[red]Error: {str(e)}[/red]")
                return False
        return False

    def analyse_with_gemini(self, question):
        if not self.tweets:
            self.console.print("[yellow]No tweets loaded.[/yellow]")
            return
            
        with Progress() as progress:
            task = progress.add_task("[cyan]Analysing...", total=100)
            
            prompt = f"""Analyze these tweets from @{self.username} to answer: {question}
            
Please provide a clear and concise analysis considering both the text content and any images present.

Tweets:
"""
            images = []
            
            for tweet in self.tweets:
                prompt += f"\nText: {tweet['text']}\n"
                metrics = tweet['metrics']
                prompt += f"Metrics: {metrics['like_count']} likes, {metrics['reply_count']} replies, {metrics['retweet_count']} retweets\n"
                
                if tweet['media']:
                    for media_path in tweet['media']:
                        img = self.load_image(media_path)
                        if img:
                            images.append(img)
            
            try:
                if images:
                    response = self.model.generate_content([prompt, *images])
                else:
                    response = self.model.generate_content(prompt)
                
                progress.update(task, advance=100)
                
                if response:
                    analysis = response.text
                    self.console.print(Panel(
                        Markdown(analysis),
                        title="Analysis",
                        border_style="cyan"
                    ))
                    
            except Exception as e:
                self.console.print(f"[red]Error during analysis: {str(e)}[/red]")

    def interactive_session(self):
        in_chat = True
        while in_chat:
            try:
                self.console.print("\n[cyan]Options:[/cyan]")
                self.console.print("1. Ask a question")
                self.console.print("2. Refresh tweets")
                self.console.print("3. Exit to user selection")
                
                choice = Prompt.ask("Choose an option", choices=["1", "2", "3"])
                
                if choice == "1":
                    while True:
                        question = Prompt.ask(f"What would you like to know about @[i][cyan]{self.username}[/cyan][/i]'s tweets? (type 'exit' to return to menu)")
                        if question.lower() == 'exit':
                            break
                        self.analyse_with_gemini(question)
                elif choice == "2":
                    if self.refresh_tweets():
                        self.console.print("[green]Tweets refreshed successfully[/green]")
                    else:
                        self.console.print("[red]Failed to refresh tweets[/red]")
                elif choice == "3":
                    in_chat = False
                    
            except KeyboardInterrupt:
                if Confirm.ask("\nDo you want to exit to user selection?"):
                    in_chat = False
                continue

def main():
    try:
        analyser = TwitterChatAnalyser()
        while True:
            try:
                username = Prompt.ask("Enter Twitter username (without @)")
                if analyser.fetch_tweets(username):
                    analyser.interactive_session()
                
                if not Confirm.ask("\nWould you like to analyze another user?"):
                    break
                    
            except KeyboardInterrupt:
                if Confirm.ask("\nDo you want to exit the program?"):
                    break
                continue
                
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    
    print("\nThanks for using the Twitter Analysis tool!")

if __name__ == "__main__":
    main()