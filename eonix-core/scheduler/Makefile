CC = gcc
CFLAGS = -O2 -Wall -Wextra -std=c11

all: simulator

simulator: simulator.c
	$(CC) $(CFLAGS) -o $@ $< -lm

test: simulator
	./simulator --algo all --input processes.csv

clean:
	rm -f simulator

.PHONY: all clean test
