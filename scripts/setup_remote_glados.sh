#!/bin/bash

# Setup script for GLaDOS remote audio functionality
# This script helps deploy GLaDOS on a remote server with microphone streaming support

set -e

echo "🤖 GLaDOS Remote Audio Setup Script"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    print_status "Docker is installed"
}

# Check if Docker Compose is installed
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    print_status "Docker Compose is installed"
}

# Create environment file
create_env_file() {
    if [ ! -f .env.remote ]; then
        print_status "Creating .env.remote file..."
        cat > .env.remote << EOF
# GLaDOS Remote Configuration
API_PORT=5050
WS_PORT=8765
GLADOS_CONFIG=/app/configs/remote_config.yaml
OLLAMA_URL=http://host.docker.internal:11434

# Optional: Set your LLM API key if needed
# API_KEY=your_api_key_here
EOF
        print_status "Created .env.remote file. Please review and update if needed."
    else
        print_status ".env.remote file already exists"
    fi
}

# Build and start GLaDOS remote service
start_glados_remote() {
    print_status "Building and starting GLaDOS remote service..."
    
    # Use docker-compose or docker compose based on what's available
    if command -v docker-compose &> /dev/null; then
        docker-compose -f docker-compose.remote.yml --env-file .env.remote up --build -d
    else
        docker compose -f docker-compose.remote.yml --env-file .env.remote up --build -d
    fi
    
    print_status "GLaDOS remote service started"
}

# Show status
show_status() {
    print_status "Checking service status..."
    
    if command -v docker-compose &> /dev/null; then
        docker-compose -f docker-compose.remote.yml ps
    else
        docker compose -f docker-compose.remote.yml ps
    fi
}

# Show logs
show_logs() {
    print_status "Showing GLaDOS logs (press Ctrl+C to exit)..."
    
    if command -v docker-compose &> /dev/null; then
        docker-compose -f docker-compose.remote.yml logs -f glados-remote
    else
        docker compose -f docker-compose.remote.yml logs -f glados-remote
    fi
}

# Install client dependencies
install_client_deps() {
    print_status "Installing client dependencies..."
    
    # Check if we're in a virtual environment
    if [[ "$VIRTUAL_ENV" != "" ]]; then
        print_status "Virtual environment detected: $VIRTUAL_ENV"
    else
        print_warning "No virtual environment detected. Consider creating one:"
        echo "  python -m venv glados_env"
        echo "  source glados_env/bin/activate"
        echo ""
    fi
    
    # Install dependencies
    pip install -e ".[remote,api]"
    
    print_status "Client dependencies installed"
}

# Test client connection
test_client() {
    print_status "Testing remote audio client..."
    
    # Check if examples/remote_audio_client.py exists
    if [ ! -f "examples/remote_audio_client.py" ]; then
        print_error "Remote audio client example not found"
        return 1
    fi
    
    # List audio devices
    print_status "Available audio devices:"
    python examples/remote_audio_client.py --list-devices
    
    echo ""
    print_warning "To test the client connection, run:"
    echo "  python examples/remote_audio_client.py --server ws://localhost:8765"
    echo ""
    print_warning "For a remote server, replace localhost with the server IP:"
    echo "  python examples/remote_audio_client.py --server ws://YOUR_SERVER_IP:8765"
}

# Show usage instructions
show_usage() {
    echo ""
    echo "🚀 GLaDOS Remote Audio Setup Complete!"
    echo "======================================"
    echo ""
    echo "📋 Usage Instructions:"
    echo ""
    echo "1. 🖥️  Server is running with the following endpoints:"
    echo "   - HTTP API: http://localhost:5050"
    echo "   - WebSocket Audio: ws://localhost:8765"
    echo ""
    echo "2. 🎤 To connect from a remote device:"
    echo "   a. Install dependencies on the client machine:"
    echo "      pip install sounddevice websockets numpy loguru"
    echo ""
    echo "   b. Run the client script:"
    echo "      python examples/remote_audio_client.py --server ws://YOUR_SERVER_IP:8765"
    echo ""
    echo "   c. Replace YOUR_SERVER_IP with your server's IP address"
    echo ""
    echo "3. 🔧 Configuration:"
    echo "   - Edit configs/remote_config.yaml to customize settings"
    echo "   - Modify .env.remote for environment variables"
    echo ""
    echo "4. 📊 Monitor the server:"
    echo "   - View logs: $0 logs"
    echo "   - Check status: $0 status"
    echo ""
    echo "5. 🛑 To stop the server:"
    echo "   $0 stop"
    echo ""
}

# Stop services
stop_services() {
    print_status "Stopping GLaDOS remote services..."
    
    if command -v docker-compose &> /dev/null; then
        docker-compose -f docker-compose.remote.yml down
    else
        docker compose -f docker-compose.remote.yml down
    fi
    
    print_status "Services stopped"
}

# Main script logic
case "${1:-setup}" in
    "setup")
        check_docker
        check_docker_compose
        create_env_file
        start_glados_remote
        install_client_deps
        show_status
        show_usage
        ;;
    "start")
        start_glados_remote
        show_status
        ;;
    "stop")
        stop_services
        ;;
    "restart")
        stop_services
        start_glados_remote
        show_status
        ;;
    "status")
        show_status
        ;;
    "logs")
        show_logs
        ;;
    "client")
        install_client_deps
        test_client
        ;;
    "test")
        print_status "Running connection test..."
        # Test if WebSocket port is open
        if nc -z localhost 8765 2>/dev/null; then
            print_status "WebSocket port 8765 is open"
        else
            print_error "WebSocket port 8765 is not accessible"
        fi
        
        # Test if HTTP API port is open
        if nc -z localhost 5050 2>/dev/null; then
            print_status "HTTP API port 5050 is open"
        else
            print_error "HTTP API port 5050 is not accessible"
        fi
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 {setup|start|stop|restart|status|logs|client|test|help}"
        echo ""
        echo "Commands:"
        echo "  setup    - Full setup (default)"
        echo "  start    - Start services"
        echo "  stop     - Stop services"
        echo "  restart  - Restart services"
        echo "  status   - Show service status"
        echo "  logs     - Show service logs"
        echo "  client   - Setup and test client"
        echo "  test     - Test connection to services"
        echo "  help     - Show this help message"
        ;;
    *)
        print_error "Unknown command: $1"
        echo "Use '$0 help' for usage information."
        exit 1
        ;;
esac
