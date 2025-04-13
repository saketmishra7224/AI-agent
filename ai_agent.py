import argparse
import json
import subprocess
import sys
import requests
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Union, Tuple

# Where we store our precious API key
CONFIG_FILE = "config.json"

@dataclass
class Message:
    """A single message in our chat - could be from the user or the AI"""
    role: str  # 'user' or 'assistant'
    content: str

@dataclass
class ExecutableStep:
    """Something we need to run - either some code or a shell command"""
    type: str  # what kind of step: 'code' or 'shell'
    content: str
    filename: Optional[str] = None  # needed when we're creating/updating files

@dataclass
class ExecutionResult:
    """What happened when we tried to run something"""
    success: bool  # did everything work?
    output: str   # what was printed
    error: Optional[str] = None  # any oopsies that happened

def load_or_create_config() -> str:
    """Try to find our API key, or ask nicely for a new one"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as config_file:
                config = json.load(config_file)
                if config.get('api_key'):
                    return config['api_key']
        except:
            # No worries if it fails, we'll just ask for a new key
            pass
    
    print("Hey! Looks like I need an OpenRouter API key to help you.")
    api_key = input("Would you mind sharing your OpenRouter API key? ")
    
    # Let's save this for next time
    try:
        with open(CONFIG_FILE, 'w') as config_file:
            json.dump({'api_key': api_key}, config_file)
        print("✨ Great! I've saved that API key for next time!")
    except Exception as e:
        print(f"😅 Oops, couldn't save the API key: {e}")
    
    return api_key

def send_prompt_to_openrouter(prompt: str, model_name: str = "mistralai/mistral-7b-instruct") -> str:
    """Let's chat with the AI model!
    
    This is where the magic happens - we send your message to the AI
    and get back its thoughtful response.
    
    Args:
        prompt: What you want to ask the AI
        model_name: Which AI model to chat with (Mistral-7B by default)
        
    Returns:
        The AI's response
        
    Raises:
        ValueError: If we can't find an API key
        requests.RequestException: If something goes wrong talking to OpenRouter
    """
    # First check if we have the key in our environment
    api_key = os.getenv('OPENROUTER_API_KEY')
    
    # If not there, check our config file
    if not api_key and os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                api_key = config.get('api_key')
        except:
            pass
    
    if not api_key:
        raise ValueError("Oops! I can't find the OpenRouter API key anywhere!")
    
    # Set up our chat with the AI
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "Your Friendly AI Assistant",
        "Content-Type": "application/json"
    }
    
    # Prepare what we want to say
    data = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a friendly and helpful AI assistant."},
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        # Let's talk to the AI!
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.RequestException as e:
        raise requests.RequestException(f"Uh oh! Couldn't chat with OpenRouter: {str(e)}")

def execute_code_and_commands(blocks: Dict[str, str], commands: List[str]) -> ExecutionResult:
    """Time to make things happen! 🚀
    
    We'll create/update any files you need and run any commands you've asked for.
    
    Args:
        blocks: Your code, organized by filename
        commands: Any shell commands you want to run
    
    Returns:
        How it all went - success or failure, output, and any oopsies
    """
    output_lines = []
    try:
        # First, let's handle any code files
        for filename, code in blocks.items():
            with open(filename, 'w') as f:
                f.write(code)
            output_lines.append(f"✨ Created/Updated {filename}")
        
        # Now let's run those commands
        for cmd in commands:
            output_lines.append(f"\n🔧 Running: {cmd}")
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.stdout:
                output_lines.append("📝 Output:")
                output_lines.append(result.stdout)
            
            if result.returncode != 0:
                error_msg = f"❌ Command failed: {cmd}\n💥 Error: {result.stderr}"
                return ExecutionResult(
                    success=False,
                    output='\n'.join(output_lines),
                    error=error_msg
                )
        
        return ExecutionResult(
            success=True,
            output='\n'.join(output_lines)
        )
        
    except Exception as e:
        return ExecutionResult(
            success=False,
            output='\n'.join(output_lines),
            error=f"💥 Oops! Something went wrong: {str(e)}"
        )

class ChatbotAgent:
    def __init__(self, api_key: str):
        """Get ready to help with coding tasks! 🤖"""
        self.api_key = api_key
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Your Coding Buddy",
            "Content-Type": "application/json"
        }
        # Start with a friendly system message
        self.conversation_history: List[Message] = [
            Message(role="system", content="""Hey there! I'm your coding buddy and I can help you with:
1. 💻 Writing code in any programming language
2. 📝 Creating and updating files
3. 🐚 Running shell commands
4. 🤝 Helping with programming questions
5. 📋 Breaking down complex tasks into simple steps

Just let me know what you need help with!""")
        ]
        
    def chat(self, user_input: str) -> str:
        """Have a chat and maybe write some code! 💭"""
        self.conversation_history.append(Message(role="user", content=user_input))
        
        try:
            # Let's see what the AI thinks about this
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json={
                    "model": "mistralai/mistral-7b-instruct",
                    "messages": [{"role": m.role, "content": m.content} for m in self.conversation_history]
                }
            )
            response.raise_for_status()
            ai_response = response.json()['choices'][0]['message']['content']
            
            # Check if we need to do anything
            code_blocks = self._extract_code_blocks(ai_response)
            shell_commands = self._extract_shell_commands(ai_response)
            
            # Make it happen!
            result = self._handle_execution(code_blocks, shell_commands)
            
            # Remember what we talked about
            self.conversation_history.append(Message(role="assistant", content=ai_response))
            
            # Put it all together nicely
            final_response = ai_response
            if result.output:
                final_response += f"\n\n📋 Here's what happened:\n{result.output}"
            if result.error:
                final_response += f"\n\n❌ Uh oh:\n{result.error}"
                
            return final_response
            
        except Exception as e:
            return f"💥 Oops! {str(e)}"
    
    def _extract_code_blocks(self, text: str) -> Dict[str, str]:
        """Find any code blocks in our conversation 🔍"""
        code_blocks = {}
        code_pattern = r"```(\w+(?:\.\w+)?)\n(.*?)```"
        
        for match in re.finditer(code_pattern, text, re.DOTALL):
            filename, code = match.groups()
            code_blocks[filename] = code.strip()
            
        return code_blocks
    
    def _extract_shell_commands(self, text: str) -> List[str]:
        """Find any shell commands we need to run 🐚"""
        shell_pattern = r"\$SHELL:\s*(.+)$"
        return [match.group(1).strip() for match in re.finditer(shell_pattern, text, re.MULTILINE)]
    
    def _handle_execution(self, code_blocks: Dict[str, str], commands: List[str]) -> ExecutionResult:
        """Time to make the magic happen! ✨"""
        return execute_code_and_commands(code_blocks, commands)

def main():
    """Let's get this party started! 🎉"""
    try:
        # First things first - we need that API key
        api_key = os.getenv('OPENROUTER_API_KEY') or load_or_create_config()
        if not api_key:
            print("❌ Oops! I need an API key to help you!")
            return 1

        print("🤖 Hi! I'm your coding assistant!")
        print("💡 I can help you write code, create files, run commands, and more!")
        print("👋 Just type 'exit' when you're done.")
        
        chatbot = ChatbotAgent(api_key)
        
        while True:
            try:
                user_input = input("\n👤 You: ").strip()
                
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    print("👋 Take care! Come back if you need more help!")
                    break
                    
                if not user_input:
                    continue
                
                print("\n🤖 Assistant: ", end="")
                response = chatbot.chat(user_input)
                print(response)
                
            except KeyboardInterrupt:
                print("\n👋 Catch you later!")
                break
            except Exception as e:
                print(f"❌ Whoops! {e}")
                
    except Exception as e:
        print(f"❌ Something unexpected happened: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())