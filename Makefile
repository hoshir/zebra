#
#  File:          Makefile
#
#  Author:        Gunnar Andersson (gunnar@radagast.se)
#
#  Created:       July 2, 1997
#


# --- Directories ---

SRCDIR   = src
DATADIR  = data
BUILDDIR = build
OBJDIR   = $(BUILDDIR)/obj
BINDIR   = $(BUILDDIR)/bin

VPATH = $(SRCDIR)


# --- Files ---

SRCS = \
	bitbcnt.c \
	bitbmob.c \
	bitboard.c \
	bitbtest.c \
	cntflip.c \
	counter.c \
	display.c \
	doflip.c \
	end.c \
	epcstat.c \
	error.c \
	eval.c \
	game.c \
	getcoeff.c \
	globals.c \
	hash.c \
	learn.c \
	midgame.c \
	moves.c \
	myrandom.c \
	opname.c \
	osfbook.c \
	patterns.c \
	pcstat.c \
	probcut.c \
	safemem.c \
	search.c \
	threads.c \
	stable.c \
	thordb.c \
	timer.c \
	unflip.c

OBJS         = $(addprefix $(OBJDIR)/,$(SRCS:.c=.o))
AUTOP_OBJ    = $(OBJDIR)/autop.o

TESTDIR  = tests

ZEBRA_EXE    = $(BINDIR)/zebra
SCRZEBRA_EXE = $(BINDIR)/scrzebra
BOOKTOOL_EXE = $(BINDIR)/booktool
PRACTICE_EXE = $(BINDIR)/practice
ENDDEV_EXE   = $(BINDIR)/enddev
TUNE8DBS_EXE = $(BINDIR)/tune8dbs
FLIPTEST_EXE = $(BINDIR)/fliptest
THREADTEST_EXE = $(BINDIR)/threadtest

LIB          = $(BUILDDIR)/libzebra.a

# Symlinks so the engine finds its data files when run from $(BINDIR)
DATA_LINKS   = $(BINDIR)/book.bin $(BINDIR)/coeffs2.bin


# --- Libraries ---

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
LDFLAGS		= -lm -lz -pthread
else
LDFLAGS		= -static -lm -lz -pthread
endif
#LDFLAGS	= -static -lm -lz -Wl,-Map,map.out


# --- Programs ---

CC              = gcc
CXX		= g++


# --- Flags ---

DEFS =		-DINCLUDE_BOOKTOOL -DTEXT_BASED -DZLIB_STATIC
THREAD_FLAGS =	-pthread

WARNINGS =	-Wall -Wcast-align -Wwrite-strings -Wstrict-prototypes -Winline
OPTS =		-O3 -fomit-frame-pointer -falign-functions=32
#OPTS =		-O3 -fomit-frame-pointer -mtune=core2 -falign-functions=32

CFLAGS =	$(OPTS) $(WARNINGS) $(DEFS) $(THREAD_FLAGS) -I$(SRCDIR) -MMD -MP
CXXFLAGS =	$(CFLAGS)


# --- Targets ---

all		: $(LIB) zebra scrzebra booktool practice enddev tune8dbs

# Convenience aliases: "make zebra" etc.
zebra		: $(ZEBRA_EXE) $(DATA_LINKS)
scrzebra	: $(SCRZEBRA_EXE) $(DATA_LINKS)
booktool	: $(BOOKTOOL_EXE) $(DATA_LINKS)
practice	: $(PRACTICE_EXE) $(DATA_LINKS)
enddev		: $(ENDDEV_EXE) $(DATA_LINKS)
tune8dbs	: $(TUNE8DBS_EXE)
libzebra.a	: $(LIB)

# --- Tests ---
#
# "make test" runs:
#  1. fliptest: differential test of the bitboard vs. board-array
#     flip implementations on random positions (see tests/fliptest.c)
#  2. check_ffo.sh: solves a fast subset of the FFO endgame test suite
#     and verifies the scores against the published answers
#
# FFO positions are solved in parallel; override the degree with
# e.g. "make test FFO_JOBS=8" (default 4).

test		: $(FLIPTEST_EXE) $(THREADTEST_EXE) scrzebra
	$(FLIPTEST_EXE)
	$(THREADTEST_EXE)
	sh $(TESTDIR)/check_ffo.sh quick $(FFO_JOBS)

# Solves ALL positions in tests/ffotest.scr and verifies the results.
# WARNING: this takes a very long time (multiple hours).
test-full	: $(FLIPTEST_EXE) $(THREADTEST_EXE) scrzebra
	$(FLIPTEST_EXE)
	$(THREADTEST_EXE)
	sh $(TESTDIR)/check_ffo.sh full $(FFO_JOBS)

$(FLIPTEST_EXE)	: $(TESTDIR)/fliptest.c $(LIB) | $(BINDIR)
	$(CC) -o $@ $(CFLAGS) $(TESTDIR)/fliptest.c $(LIB) $(LDFLAGS)

$(THREADTEST_EXE)	: $(TESTDIR)/threadtest.c $(LIB) | $(BINDIR)
	$(CC) -o $@ $(CFLAGS) $(TESTDIR)/threadtest.c $(LIB) $(LDFLAGS)

.PHONY		: all clean test test-full zebra scrzebra booktool practice enddev tune8dbs libzebra.a

$(ZEBRA_EXE)	: $(OBJS) $(OBJDIR)/zebra.o $(AUTOP_OBJ) | $(BINDIR)
	$(CC) -o $@ $(CFLAGS) $(OBJS) $(OBJDIR)/zebra.o $(AUTOP_OBJ) $(LDFLAGS)

$(SCRZEBRA_EXE)	: $(OBJS) $(OBJDIR)/scrzebra.o $(AUTOP_OBJ) | $(BINDIR)
	$(CC) -o $@ $(CFLAGS) $(OBJS) $(OBJDIR)/scrzebra.o $(AUTOP_OBJ) $(LDFLAGS)

$(BOOKTOOL_EXE)	: $(OBJS) $(OBJDIR)/booktool.o $(AUTOP_OBJ) | $(BINDIR)
	$(CC) -o $@ $(CFLAGS) $(OBJS) $(OBJDIR)/booktool.o $(AUTOP_OBJ) $(LDFLAGS)

$(PRACTICE_EXE)	: $(OBJS) $(OBJDIR)/practice.o $(AUTOP_OBJ) | $(BINDIR)
	$(CC) -o $@ $(CFLAGS) $(OBJS) $(OBJDIR)/practice.o $(AUTOP_OBJ) $(LDFLAGS)

$(ENDDEV_EXE)	: $(OBJS) $(OBJDIR)/enddev.o $(AUTOP_OBJ) | $(BINDIR)
	$(CC) -o $@ $(CFLAGS) $(OBJS) $(OBJDIR)/enddev.o $(AUTOP_OBJ) $(LDFLAGS)

$(TUNE8DBS_EXE)	: $(OBJDIR)/tune8dbs.o | $(BINDIR)
	$(CC) -o $@ $(CFLAGS) $(OBJDIR)/tune8dbs.o $(LDFLAGS)

$(LIB)		: $(OBJS)
	ar rcv $@ $(OBJS)
	ranlib $@

$(OBJDIR)/%.o	: %.c | $(OBJDIR)
	$(CC) $(CFLAGS) -c -o $@ $<

$(BINDIR)/book.bin	: | $(BINDIR)
	ln -sf ../../$(DATADIR)/book.bin $@

$(BINDIR)/coeffs2.bin	: | $(BINDIR)
	ln -sf ../../$(DATADIR)/coeffs2.bin $@

$(OBJDIR) $(BINDIR):
	mkdir -p $@

clean		:
	$(RM) -r $(BUILDDIR)

zsrc:
	tar cf zebra.tar $(SRCDIR) Makefile \
	$(DATADIR)/openings.txt LICENSE README.md
	gzip --best -f zebra.tar

# Auto-generated header dependencies (via -MMD)
-include $(wildcard $(OBJDIR)/*.d)
