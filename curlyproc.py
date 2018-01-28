#
# Process message body, applying preprocessor {{ }} transformations to the html / text
#
from enum import Enum, auto
import time, sys, json
from requests import request
#
# Preprocessor transform request
preProcessorRequest = 'x-url'

class Tok(Enum):
    # raw lexer token types
    STRING = auto()
    WHITESPACE = auto()
    OPEN_2CURLY = auto()
    CLOSE_2CURLY = auto()
    OPEN_3CURLY = auto()
    CLOSE_3CURLY = auto()
    # higher level parsed expression token types
    HBARS_START = auto()
    HBARS_END = auto()
    PREPROCESSOR_START = auto()
    PREPROCESSOR_END = auto()

#
# Character tokenizer for handlebars language. Distinguishes between {{ }} {{{ }}} whitespace and other strings
# s is a complete input string.  To keep from unnecessary rewriting, we tokenize from point p onwards.
# Returns: token type, value string, new value of p.
#
# 0 <= p < len(s)
#
def getToken(s, p, nest):
    tok = None
    sOut = ''
    if not p < len(s):
        return None, '', p, nest                        # Run out of strings - return error
    # check for special digram and trigrams
    if s[p] == '{':
        sOut += s[p]; p += 1
        if p < len(s) and s[p] == '{':                  # Got a {{
            sOut += s[p]; p += 1
            if p < len(s) and s[p] == '{':              # Got a {{{
                sOut += s[p]; p += 1
                tok = Tok.OPEN_3CURLY
                nest += 1
                return tok, sOut, p, nest
            else:
                tok = Tok.OPEN_2CURLY
                nest += 1
                return tok, sOut, p, nest
        # else fall through and treat { as beginning of generic string

    elif s[p] == '}':
        sOut += s[p]; p += 1
        if p < len(s) and s[p] == '}':                  # Got a }}
            sOut += s[p]; p += 1
            if p < len(s) and s[p] == '}':              # Got a }}}
                sOut += s[p]; p += 1
                tok = Tok.CLOSE_3CURLY
                nest -= 1
                return tok, sOut, p, nest
            else:
                tok = Tok.CLOSE_2CURLY
                nest -= 1
                return tok, sOut, p, nest
        # else fall through and treat } as beginning of generic string

    elif s[p].isspace():
        # Absorb one or more whitespaces
        while p < len(s) and s[p].isspace():
            sOut += s[p]; p += 1
        tok = Tok.WHITESPACE
        return tok, sOut, p, nest

    # Generic string, which might already include single { or } from misses above.
    # If we're at nonzero nest level (i.e. inside a curly), then split tokens on whitespace
    while p < len(s) and not (s[p] == '{' or s[p] == '}' or (nest >0 and s[p].isspace()) ):
        sOut += s[p]; p += 1
    tok = Tok.STRING
    return tok, sOut, p, nest

#
# Handle the contents of a substitution expression, which may contain (nested) expressions
# The expression may start/end with balanced double or triple curlies
#
def getCurlyExpr(s, p, nest, t):
    if t == Tok.OPEN_2CURLY:
        toks = [ {'tok': Tok.HBARS_START, 'str': '{{'} ]
        closeType = Tok.CLOSE_2CURLY
        finishType = {'tok': Tok.HBARS_END, 'str': '}}'}
    elif t == Tok.OPEN_3CURLY:
        toks = [ {'tok': Tok.HBARS_START, 'str': '{{{'} ]
        closeType = Tok.CLOSE_3CURLY
        finishType = {'tok': Tok.HBARS_END, 'str': '}}}'}
    else:
        print('Unexpected token type', t)
        return None

    preprocWord = 0                                         # state variable, detects start of a preprocessor req
    while p < len(s):
        t, v, p, nest = getToken(s, p, nest)

        if t == Tok.OPEN_2CURLY or t == Tok.OPEN_3CURLY:
            # Handle nested expressions
            subtoks, p, nest = getCurlyExpr(s, p, nest, t)
            if subtoks:
                toks.extend(subtoks)

        elif t == Tok.STRING:
            if preprocWord == 0:
                if v == preProcessorRequest:
                    toks[-1]['tok'] = Tok.PREPROCESSOR_START # change the token start & end type
                    toks[-1]['str'] = v
                    finishType['tok'] = Tok.PREPROCESSOR_END
                    preprocWord += 1
                else:
                    toks[-1]['str'] += v                    # accumulate strings in usual HBARS req
            else:
                toks.append({'tok': t, 'str': v})           # accumulate further pre-proc strings in separate tokens, for ease of parsing

        elif t == Tok.WHITESPACE:
            toks[-1]['str'] += v                            # accumulate strings in usual HBARS or PREPROCESSOR req

        elif t == closeType:
            # Correct matching brackets closure - finish off
            toks.append(finishType)
            break
        else:
            print('Unexpected token type', t)
            return None
    return toks, p, nest

#
# Transform a string that may contain preprocessor requests in to a list of token types/values.  Respects whitespace and nesting.
# Parse s, looking for {{.  If a preprocessor req found, get the contents up to the matching }}, preserving
# nesting, and perform any inner substitutions needed.
# p is a positional pointer, which is in-place updated by the tokenizer.
#
def transformReq(s):
    p = 0
    nest = 0
    tokens = []
    while p < len(s):
        t, v, p, nest = getToken(s, p, nest)
        if t == Tok.STRING or t == Tok.WHITESPACE:
            tokens.append({'tok': t, 'str': v})
        elif t == Tok.OPEN_2CURLY or t == Tok.OPEN_3CURLY :
            toks, p, nest = getCurlyExpr(s, p, nest, t)
            if nest > 0:
                print('Warning: missing closing handlebars to match', v, toks[0]['str'] )
            if toks:
                tokens.extend(toks)
        else:
            print('Unexpected token {:20}'.format(t), '{:60.40}'.format(v.replace('\n','.').replace('\t','.')), len(v), 'bytes')
    return tokens


#
# -----------------------------------------------------------------------------------------
# Helper functions for the token parser
# -----------------------------------------------------------------------------------------
#
# From https://developers.sparkpost.com/api/substitutions-reference.html
# Substitution keys can be composed of any string of US-ASCII letters, digits, and underscores, not beginning with a digit, with the exception of the following keywords:
#
def isValidJSONName(v):
    # check against list of unsupported sub key names
    if v in ['and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function', 'if', 'in', 'local', 'nil', 'not', 'or', 'each', 'repeat', 'return', 'then', 'true', 'until', 'while']:
        print('External requests don\'t support', sOut, ' keyword.  See https://developers.sparkpost.com/api/substitutions-reference.html')
        return False
    else:
        return v.isidentifier()                                 # use Python's definition

# JSON-format variable references are supported as per https://developers.sparkpost.com/api/substitutions-reference.html, i.e.
#
#   var
#   var.var
#   var[idx]
#   var[idx].var            and nestings thereof
#
# JSON arrays are zero-based so 0<= idx < len
#   idx can be a numeric constant or (more usually) another var
#
# If value not found, return None
#
def accessSubData(sub, v):
    if isValidJSONName(v) and v in sub:
        return sub[v]
    else:
        i = 0
        while i<len(v):
            if v[i] == '.':
                # found a structure separator
                a = v[0:i]                      # part up to, but not including the dot
                rhs = v[i+1:]                   # trailing part after the dot
                if isValidJSONName(a) and a in sub:
                    return accessSubData(sub[a], rhs)       # follow the reference down
            elif v[i] == '[':
                # found an array index
                a = v[0:i]                      # leading part up to, but not including the [
                b = v[i+1:]                     # trailing part
                idx, closebr, rhs = b.partition(']')
                if closebr != ']':
                    print('Invalid array index in ', v)
                    return None
                if not idx.isnumeric():
                    idx = accessSubData(sub, idx)           # resolve a variable index
                if len(rhs) > 0 and rhs[0] == '.':
                    rhs = rhs[1:]                           # Looking good - we need to strip the dot
                    # resolve the LHS name and the index, continue downwards with the RHS
                    if a in sub:
                        idx = int(idx)
                        if len(sub[a]) > idx:               # we have some data
                            return accessSubData(sub[a][idx], rhs)
                        else:
                            return None                     # silent return, as data may be in another scope
                    else:
                        return None
                else:
                    if a in sub:                            # form var[idx]
                        idx = int(idx)
                        if len(sub[a]) > idx:               # we have some data
                            res = (sub[a][idx])
                            return res
                    return None
            else:
                i += 1
        return None
#
# Found a regular Handlebars token inside a preprocessor token. We attempt to resolve the Handlebars expression using the
# provided substitution_data (per recipient and global).
#
# Currently the only handlebars expression type supported is a variable reference, not conditional logic or 'each' looping;
# that seems reasonable given that we should resolve down to a single url-string anyway.
#
# Nested expressions are allowed, the intention is to allow replacement of any part of the request e.g.
#   {{x-url get https://blah.com?{{foo}}
#   {{x-url get https://blah.com?{{foo.{{bar}} }}
#   {{x-url {{foo}} }}
# and even have a url return a url e.g.
#   {{x-url {{x-url {{foo}} }} }}
#
def preProcessorGetHbars(tokens, i, substitution_data):
    assert tokens[i]['tok'] == Tok.HBARS_START
    s = tokens[i]['str'].lstrip('{')             # Get the first keyword
    i += 1
    while i < len(tokens):
        t = tokens[i]['tok']
        if t == Tok.STRING:
            s += t['str']
            i += 1
        elif t == Tok.WHITESPACE:
            i += 1                                  # Whitespace silently absorbed within hbars
        elif t == Tok.HBARS_END:
            i += 1
            break                                   # outer level doesn't need to see this token - return what we've got so far
        elif t == Tok.PREPROCESSOR_START:
            s, i = preProcessor(tokens, i)          # Allow preproc req within a hbars req .. why not
            s += s
        elif t == Tok.HBARS_START:
            s, i = preProcessorGetHbars(tokens, i) # Allow hbars req within a hbars req .. why not
            s += s
        else:
            print('Unexpected token: ', t['tok'], '=', t['str'], 'inside preprocessor clause')
            return None
    # Got the accumulated hbars content in s.  Look up in our sub variables.  Precedence is per-recipient, then global
    sOut = accessSubData(substitution_data['recipient'], s)
    if sOut == None:
        sOut = accessSubData(substitution_data['global'], s)
        if sOut == None:
            print('Error: variable', sOut, 'not found')
            SOut = ''
    return sOut, i


def preProcessorGetWord(tokens, i, substitution_data):
    sOut = ''
    while True:
        tt = tokens[i]['tok']
        if tt == Tok.STRING:
            sOut += tokens[i]['str']            # String literal
            i += 1
        elif tt == Tok.WHITESPACE:              # Skip when inside preprocessor
            i += 1
            break                               # Whitespace signals end of a word, as spaces not valid within URL
        elif tt == Tok.PREPROCESSOR_END:
            break                               # Get out without advancing the pointer, outer level also needs to see this token
        elif tt == Tok.PREPROCESSOR_START:
            s, i = preProcessor(tokens, i, substitution_data)   # Allow preproc req within a preproc req?  Why not .. down the rabbit-hole we go!
            sOut += s
        elif tt == Tok.HBARS_START:
            s, i = preProcessorGetHbars(tokens, i, substitution_data)
            sOut += s
        else:
            print('Unexpected token: ', t['tok'], '=', t['str'], 'inside preprocessor clause')
            return None
    return sOut, i

#
# Act on preprocessor requests within the token stream
# Expected syntax: {{x-url method url}}
#   {{x-url is already absorbed and represented by the token
#   method and url are read from non-whitespace tokens, up to the end token (which represents the }} )
#
# substitution_data is passed through, as words in the request may themselves have {{ }} substitutions
#
def preProcessor(tokens, i, substitution_data):
    assert tokens[i]['tok'] == Tok.PREPROCESSOR_START and tokens[i]['str'].strip(' ') == preProcessorRequest
    sOut = ''
    i += 1
    req, i = preProcessorGetWord(tokens, i, substitution_data)          # Will expand any inline substitution_data refs for us
    if tokens[i]['tok'] == Tok.PREPROCESSOR_END:
        r = req.split(' ')
        method = r[0].lower()                                           # http method
        if method == 'get':
            # Got url in r[1]
            response = request(method, r[1])
            print('Preprocess request URL', req, 'returned status code', response.status_code, len(response.text), 'bytes content')
            if response.status_code == 200:
                sOut = response.text
        else:
            print('Unsupported method', method, 'in preprocessor request:', req)
    else:
        print('Unexpected info in preprocessor request: ', req, tokens[i]['str'])
    return sOut, i                                                      # And we're done

#
# Generate an output string from tokens and substitution_data
#
def tokensToString(tokens, substitution_data):
    sOut = ''
    i = 0  # Can't use for, as preprocessor needs to advance index inside loop
    while i < len(tokens):
        if tokens[i]['tok'] == Tok.PREPROCESSOR_START:
            # absorb variable number of tokens, returning the final text / html string
            s, i = preProcessor(tokens, i, substitution_data)
        else:
            s = tokens[i]['str']
        sOut += s
        i += 1
    return sOut

# -----------------------------------------------------------------------------------------
# Main code
# -----------------------------------------------------------------------------------------
#
# Simple test cases
#a = (transformReq(' initial text then {{ hello with spaces }} inside a curly but { this } {is} single curlies'))
#a = (transformReq(' initial text then {{ hello with spaces }} inside a curly but { this } {is} single curlies and } this is a lone close'))
#a = (transformReq(' special chars 0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz_ !"#$%& \'()*+,-./ :;<=>?@ []^_` {|}~'))
#a = (transformReq(' special chars !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`abcdefghijklmnopqrstuvwxyz{|}~ {{ hello inside a curly }}'))
#a = (transformReq('  {{ {{ hello }}  inside a curly }}  '))

t1 = time.time()

# TODO: metadata also allowed in sub-data
substitution_data = {
    'recipient': {
        'name': 'billybob',
        'message_id': 'SPARKPOST_TEST',
        'email_hash': '125'
},
    'global': {
        'subject': 'Avocados for all',
        'batch_id': 'SPARKPOST_TEST',
        'auth_token': 'LuXBxonPIvZGkDz0qTeB6PIOqIyxq8Va',
        'abc': {
            'def': 'ghi'
        },
        'jkl': [
            'mno',
            'pqr',
            { 'stu': 'yz' }
        ],
    }
}
#
# preprocessor unit tests
#
def testPreprocessor(s, substitution_data, compUrl):
    tokens = transformReq(s)
    i = 0
    while i < len(tokens) and tokens[i]['tok'] != Tok.PREPROCESSOR_START:
        i += 1
    assert tokens[i]['tok'] == Tok.PREPROCESSOR_START
    sOut, i = preProcessorGetWord(tokens, i+1, substitution_data)
    print(compUrl, 'resolves to', sOut)
    if sOut != compUrl:
        exit(1)
#
# Check JSON variable resolution within x-urls works as expected
#
testPreprocessor('Hello World {{x-url get https://fred.com?id={{email_hash}} }}', substitution_data, 'get https://fred.com?id=125')
testPreprocessor('Hello World {{x-url get https://fred.com?id={{subject}} }}', substitution_data, 'get https://fred.com?id=Avocados for all')
testPreprocessor('Hello World {{x-url get https://foo.com?id={{jkl[2].stu}} }}', substitution_data, 'get https://foo.com?id=yz')
testPreprocessor('Hello World {{x-url get http://bar.com?id={{jkl[0]}} }}', substitution_data, 'get http://bar.com?id=mno')

"""
# Get complex test case from an input file
infile = sys.argv[1]
with open(infile, 'r') as f:
    tokens = transformReq(f.read())    
    sOut = tokensToString(tokens, substitution_data)
    if sOut != None:
        with open('test-out.html', 'w') as outfile:
            outfile.write(sOut)
"""

t2 = time.time() - t1
print(t2, 'seconds')