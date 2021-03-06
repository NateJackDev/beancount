"""Flag constants.
"""
__author__ = "Martin Blais <blais@furius.ca>"


# Special flags;  pylint: disable=bad-whitespace
#
# Note: These need to be kept in sync with the lexer's FLAG token, in order to
# allow round-trips between text and in-memory entries to work.
# {5307d8fa1e7b}
FLAG_OKAY        = '*' # Transactions that have been checked.
FLAG_WARNING     = '!' # Mark by the user as something to be looked at later on.
FLAG_PADDING     = 'P' # Transactions created from padding directives.
FLAG_SUMMARIZE   = 'S' # Transactions created due to summarization.
FLAG_TRANSFER    = 'T' # Transactions created due to balance transfers.
FLAG_CONVERSIONS = 'C' # Transactions created to account for price conversions.
FLAG_UNREALIZED  = 'U' # Transactions created due to unrealized gains.
FLAG_RETURNS     = 'R' # Transactions that were internalized by returns algorithm.
