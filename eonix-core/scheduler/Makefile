CC = gcc
CFLAGS = -O2 -Wall -Wextra -std=c11 -lm

all: simulator

simulator: simulator.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f simulator

.PHONY: all clean
