#!/bin/bash
pkill -f "python.*main.py" 2>/dev/null && echo "Clickless stopped." || echo "Clickless is not running."
