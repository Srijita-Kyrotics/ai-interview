"""Real test cases for coding questions that shipped with placeholders.

Each entry maps a question id to a list of ``[input, expected]`` pairs.
``input`` is fed to the program's stdin; ``expected`` is compared against
stdout (normalized). Conventions mirror questions 1-37:
  * integers/floats/strings raw on a line
  * arrays -> space-separated numbers
  * multiple parameters -> one logical value per line
  * matrices -> one row per line (numbers space-separated, chars contiguous)
  * binary trees -> single line level-order with ``null`` for missing nodes
  * linked lists -> space-separated values on one line
  * booleans -> lowercase ``true``/``false``
Design/data-structure problems use an operation-per-line protocol where the
program prints one result per output line.
"""

TEST_CASES: dict[int, list[list[str]]] = {
    38: [
        ["3 9 20 null null 15 7\n", "3"],
        ["1 null 2\n", "2"],
        ["1 2\n", "2"],
    ],
    39: [
        ["1 2 3\n1 2 3\n", "true"],
        ["1 2\n1 null 2\n", "false"],
        ["1 2 1\n1 1 2\n", "false"],
    ],
    40: [
        ["4 2 7 1 3 6 9\n", "4 7 2 9 6 3 1"],
        ["2 1 3\n", "2 3 1"],
        ["1 2\n", "1 null 2"],
    ],
    41: [
        ["1 2 3 4 5\n", "3"],
        ["1 2\n", "1"],
        ["1\n", "0"],
    ],
    42: [
        ["3 4 5 1 2\n4 1 2\n", "true"],
        ["3 4 5 1 2 null null null null 0\n4 1 2\n", "false"],
        ["1\n1\n", "true"],
    ],
    43: [
        ["3 9 20 null null 15 7\n", "true"],
        ["1 2 2 3 3 null null 4 4\n", "false"],
        ["1 2 3\n", "true"],
    ],
    44: [
        [
            "push -2\npush 0\npush -3\ngetMin\npop\ntop\ngetMin\n",
            "-3\n0\n-2",
        ],
        ["push 1\npush 2\ntop\ngetMin\npop\ntop\n", "2\n1\n1"],
        ["push 5\ngetMin\npush 4\ngetMin\npop\ngetMin\n", "5\n4\n5"],
    ],
    45: [
        ["push 1\npush 2\npeek\npop\nempty\n", "1\n1\nfalse"],
        ["push 10\npush 20\npop\npeek\npush 30\npop\n", "10\n20\n20"],
        ["empty\npush 7\nempty\npop\nempty\n", "true\nfalse\n7\ntrue"],
    ],
    46: [
        ["3 2 0 -4\n1\n", "true"],
        ["1 2\n0\n", "true"],
        ["1\n-1\n", "false"],
    ],
    47: [
        ["1 2 4\n1 3 4\n", "1 1 2 3 4 4"],
        ["1 3 5\n2 4 6\n", "1 2 3 4 5 6"],
        ["\n0\n", "0"],
    ],
    48: [
        ["1 2 3 4 5\n", "3"],
        ["1 2 3 4 5 6\n", "4"],
        ["1\n", "1"],
    ],
    49: [
        ["1 2 3 4 5\n2\n", "1 2 3 5"],
        ["1 2 3\n3\n", "2 3"],
        ["1\n1\n", ""],
    ],
    50: [
        ["1 2 3 4 5\n", "5 4 3 2 1"],
        ["1 2\n", "2 1"],
        ["\n", ""],
    ],
    51: [
        ["-1 0 1 2 -1 -4\n", "-1 -1 2\n-1 0 1"],
        ["0 1 1\n", ""],
        ["0 0 0\n", "0 0 0"],
    ],
    52: [
        ["1 8 6 2 5 4 8 3 7\n", "49"],
        ["1 1\n", "1"],
        ["4 3 2 1 4\n", "16"],
    ],
    53: [
        ["eat tea tan ate nat bat\n", "ate eat tea\nbat\nnat tan"],
        ["\n", ""],
        ["a\n", "a"],
    ],
    54: [
        ["abcabcbb\n", "3"],
        ["bbbbb\n", "1"],
        ["pwwkew\n", "3"],
    ],
    55: [
        ["babad\n", "aba"],
        ["cbbd\n", "bb"],
        ["a\n", "a"],
    ],
    56: [
        ["PAYPALISHIRING\n3\n", "PAHNAPLSIIGYIR"],
        ["PAYPALISHIRING\n4\n", "PINALSIGYAHRPI"],
        ["A\n1\n", "A"],
    ],
    57: [
        ["3\n", "III"],
        ["58\n", "LVIII"],
        ["1994\n", "MCMXCIV"],
    ],
    58: [
        [
            "23\n",
            "ad\nae\naf\nbd\nbe\nbf\ncd\nce\ncf",
        ],
        ["2\n", "a\nb\nc"],
        [
            "79\n",
            "pw\npx\npy\npz\nqw\nqx\nqy\nqz\nrw\nrx\nry\nrz\nsw\nsx\nsy\nsz",
        ],
    ],
    59: [
        ["3\n", "((()))\n(()())\n(())()\n()(())\n()()()"],
        ["2\n", "(())\n()()"],
        ["1\n", "()"],
    ],
    60: [
        ["4 5 6 7 0 1 2\n0\n", "4"],
        ["4 5 6 7 0 1 2\n3\n", "-1"],
        ["1\n0\n", "-1"],
    ],
    61: [
        ["3 4 5 1 2\n", "1"],
        ["4 5 6 7 0 1 2\n", "0"],
        ["11 13 15 17\n", "11"],
    ],
    62: [
        ["2 3 6 7\n7\n", "2 2 3\n7"],
        ["2 3 5\n8\n", "2 2 2 2\n2 3 3\n3 5"],
        ["2\n1\n", ""],
    ],
    63: [
        [
            "1 2 3\n",
            "1 2 3\n1 3 2\n2 1 3\n2 3 1\n3 1 2\n3 2 1",
        ],
        ["0 1\n", "0 1\n1 0"],
        ["1\n", "1"],
    ],
    64: [
        ["1 2 3\n", "\n1\n1 2\n1 2 3\n1 3\n2\n2 3\n3"],
        ["0\n", "\n0"],
        ["1 2\n", "\n1\n1 2\n2"],
    ],
    65: [
        ["ABCE\nSFCS\nADEE\nABCCED\n", "true"],
        ["ABCE\nSFCS\nADEE\nABCB\n", "false"],
        ["A\nA\n", "true"],
    ],
    66: [
        ["12\n", "2"],
        ["226\n", "3"],
        ["06\n", "0"],
    ],
    67: [
        ["2\n", "2"],
        ["3\n", "3"],
        ["4\n", "5"],
    ],
    68: [
        ["3 7\n", "28"],
        ["3 2\n", "3"],
        ["1 1\n", "1"],
    ],
    69: [
        ["1 3 1\n1 5 1\n4 2 1\n", "7"],
        ["1 2 3\n4 5 6\n", "12"],
        ["1\n", "1"],
    ],
    70: [
        ["2 0 2 1 1 0\n", "0 0 1 1 2 2"],
        ["2 0 1\n", "0 1 2"],
        ["1 0\n", "0 1"],
    ],
    71: [
        ["1 2 3\n", "1 3 2"],
        ["3 2 1\n", "1 2 3"],
        ["1 1 5\n", "1 5 1"],
    ],
    72: [
        ["1 3 5 7\n10 11 16 20\n23 30 34 60\n3\n", "true"],
        ["1 3 5 7\n10 11 16 20\n23 30 34 60\n13\n", "false"],
        ["1\n1\n", "true"],
    ],
    73: [
        ["1 2 3 1\n", "2"],
        ["1 2 1 3 5 6 4\n", "5"],
        ["1\n", "0"],
    ],
    74: [
        ["3 2 1 5 6 4\n2\n", "5"],
        ["3 2 3 1 2 4 5 5 6\n4\n", "4"],
        ["1\n1\n", "1"],
    ],
    75: [
        ["1 1 1 2 2 3\n2\n", "1 2"],
        ["1 2\n2\n", "1 2"],
        ["5 5 5 5\n1\n", "5"],
    ],
    76: [
        ["1 2 3 4\n", "24 12 8 6"],
        ["-1 1 0 -3 3\n", "0 0 9 0 0"],
        ["2 3\n", "3 2"],
    ],
    77: [
        ["2 3 -2 4\n", "6"],
        ["-2 0 -1\n", "0"],
        ["-2 3 -4\n", "24"],
    ],
    78: [
        ["1 2 3 1\n", "4"],
        ["2 7 9 3 1\n", "12"],
        ["2 1\n", "2"],
    ],
    79: [
        ["1 2 5\n11\n", "3"],
        ["2\n3\n", "-1"],
        ["1\n0\n", "0"],
    ],
    80: [
        ["leetcode\nleet code\n", "true"],
        ["applepenapple\napple pen\n", "true"],
        ["catsandog\ncats dog sand and cat\n", "false"],
    ],
    81: [
        [
            "2\nput 1 1\nput 2 2\nget 1\nput 3 3\nget 2\nput 4 4\nget 1\nget 3\nget 4\n",
            "1\n-1\n-1\n3\n4",
        ],
        ["1\nput 1 1\nget 1\nput 2 2\nget 1\nget 2\n", "1\n-1\n2"],
        ["2\nput 1 1\nput 2 2\nput 3 3\nget 2\nget 3\n", "2\n3"],
    ],
    82: [
        [
            "insert apple\nsearch apple\nsearch app\nstartsWith app\ninsert app\nsearch app\n",
            "true\nfalse\ntrue\ntrue",
        ],
        ["insert a\nstartsWith a\nstartsWith b\n", "true\nfalse"],
        ["search abc\ninsert abc\nsearch abc\nstartsWith abc\n", "false\ntrue\ntrue"],
    ],
    83: [
        ["11000\n11000\n00100\n00011\n", "3"],
        ["111\n010\n111\n", "1"],
        ["000\n000\n", "0"],
    ],
    84: [
        ["4\n1 2 4\n2 1 3\n3 2 4\n4 1 3\n", "1 2 4\n2 1 3\n3 2 4\n4 1 3"],
        ["2\n1 2\n2 1\n", "1 2\n2 1"],
        ["1\n1\n", "1"],
    ],
    85: [
        ["2\n1 0\n", "true"],
        ["2\n1 0\n0 1\n", "false"],
        ["4\n1 0\n2 0\n3 1\n3 2\n", "true"],
    ],
    86: [
        [
            "1 2 2 3 5\n3 2 3 4 4\n2 4 5 3 1\n6 7 1 4 5\n5 1 1 2 4\n",
            "0 4\n1 3\n1 4\n2 2\n3 0\n3 1\n4 0",
        ],
        ["1 1\n1 1\n", "0 0\n0 1\n1 0\n1 1"],
        ["1 2 3\n", "0 0\n0 1\n0 2"],
    ],
    87: [
        ["3 9 20 null null 15 7\n", "3\n9 20\n15 7"],
        ["1\n", "1"],
        ["1 2 null 3\n", "1\n2\n3"],
    ],
    88: [
        ["2 1 3\n", "true"],
        ["5 1 4 null null 3 6\n", "false"],
        ["1\n", "true"],
    ],
    89: [
        ["3 1 4 null 2\n1\n", "1"],
        ["5 3 6 2 4 null null 1\n3\n", "3"],
        ["1\n1\n", "1"],
    ],
    90: [
        ["6 2 8 0 4 7 9 null null 3 5\n2\n8\n", "6"],
        ["6 2 8 0 4 7 9 null null 3 5\n2\n4\n", "2"],
        ["2 1\n2\n1\n", "2"],
    ],
    91: [
        ["1 2 3 null null 4 5\n", "1 2 3 null null 4 5"],
        ["1 2 null 3\n", "1 2 null 3"],
        ["1\n", "1"],
    ],
    92: [
        ["1 2 5 3 4 null 6\n", "1 2 3 4 5 6"],
        ["1 2 null 3\n", "1 2 3"],
        ["1 null 2\n", "1 2"],
    ],
    93: [
        ["1 3 2 5 3 null 9\n", "4"],
        ["1 3 2 5\n", "2"],
        ["1 3 2 5 null null 9 6 null null null null null null 7\n", "8"],
    ],
    94: [
        ["1 1 1\n2\n", "2"],
        ["1 2 3\n3\n", "2"],
        ["1 -1 0\n0\n", "3"],
    ],
    95: [
        ["1 3 -1 -3 5 3 6 7\n3\n", "3 3 5 5 6 7"],
        ["1\n1\n", "1"],
        ["1 -1\n1\n", "1 -1"],
    ],
    96: [
        ["cbaebabacd\nabc\n", "0 6"],
        ["abab\nab\n", "0 1 2"],
        ["abc\ncba\n", "0"],
    ],
    97: [
        ["10 9 2 5 3 7 101 18\n", "4"],
        ["0 1 0 3 2 3\n", "4"],
        ["7 7 7 7\n", "1"],
    ],
    98: [
        ["horse\nros\n", "3"],
        ["intention\nexecution\n", "5"],
        ["a\nb\n", "1"],
    ],
    99: [
        ["3 9 20 null null 15 7\n", "3\n20 9\n15 7"],
        ["1\n", "1"],
        ["1 2 3 4 null null 5\n", "1\n3 2\n4 5"],
    ],
    100: [
        ["3 9 20 15 7\n9 3 15 20 7\n", "3 9 20 null null 15 7"],
        ["-1\n-1\n", "-1"],
        ["1 2 3\n2 1 3\n", "1 2 3"],
    ],
    101: [
        ["1 2 3\n4 5 6\n7 8 9\n", "7 4 1\n8 5 2\n9 6 3"],
        ["5 1 9 11\n2 4 8 10\n13 3 6 7\n15 14 12 16\n", "15 13 2 5\n14 3 4 1\n12 6 8 9\n16 7 10 11"],
        ["1\n", "1"],
    ],
    102: [
        ["1 2 3\n4 5 6\n7 8 9\n", "1 2 3 6 9 8 7 4 5"],
        ["1 2 3 4\n5 6 7 8\n9 10 11 12\n", "1 2 3 4 8 12 11 10 9 5 6 7"],
        ["1\n", "1"],
    ],
    103: [
        ["1 1 1\n1 0 1\n1 1 1\n", "1 0 1\n0 0 0\n1 0 1"],
        ["0 1 2 0\n3 4 5 2\n1 3 1 5\n", "0 0 0 0\n0 4 5 0\n0 3 1 0"],
        ["1 2\n3 4\n", "1 2\n3 4"],
    ],
    104: [
        ["100 4 200 1 3 2\n", "4"],
        ["0 3 7 2 5 8 4 6 0 1\n", "9"],
        ["1 2 0 1\n", "3"],
    ],
    105: [
        ["1 3\n2 6\n8 10\n15 18\n", "1 6\n8 10\n15 18"],
        ["1 4\n4 5\n", "1 5"],
        ["6 8\n1 9\n2 4\n", "1 9"],
    ],
    106: [
        ["2\n1 3\n6 9\n2 5\n", "1 5\n6 9"],
        ["5\n1 2\n3 5\n6 7\n8 10\n12 16\n4 8\n", "1 2\n3 10\n12 16"],
        ["1\n5 7\n2 3\n", "2 3\n5 7"],
    ],
    107: [
        ["A A A B B B\n2\n", "8"],
        ["A C A B D B\n1\n", "6"],
        ["A A A\n1\n", "5"],
    ],
    108: [
        ["73 74 75 71 69 72 76 73\n", "1 1 4 2 1 1 0 0"],
        ["30 40 50 60\n", "1 1 1 0"],
        ["30 60 90\n", "1 1 0"],
    ],
    109: [
        ["2 1 + 3 *\n", "9"],
        ["4 13 5 / +\n", "6"],
        ["10 6 9 3 + -11 * / * 17 + 5 +\n", "22"],
    ],
    110: [
        ["3[a]2[bc]\n", "aaabcbc"],
        ["3[a2[c]]\n", "accaccacc"],
        ["2[abc]3[cd]ef\n", "abcabccdcdcdef"],
    ],
    111: [
        ["/home/\n", "/home"],
        ["/a/./b/../../c/\n", "/c"],
        ["/../\n", "/"],
    ],
    112: [
        ["1 3 4 2 2\n", "2"],
        ["3 1 3 4 2\n", "3"],
        ["1 1\n", "1"],
    ],
    113: [
        ["5\n", "1\n1 1\n1 2 1\n1 3 3 1\n1 4 6 4 1"],
        ["1\n", "1"],
        ["3\n", "1\n1 1\n1 2 1"],
    ],
    114: [
        ["2 3 1 1 4\n", "true"],
        ["3 2 1 0 4\n", "false"],
        ["0\n", "true"],
    ],
    115: [
        ["1 2 3 4 5\n3 4 5 1 2\n", "3"],
        ["2 3 4\n3 4 3\n", "-1"],
        ["1 2\n2 1\n", "1"],
    ],
    116: [
        ["ababcbacadefegdehijhklij\n", "9 7 8"],
        ["eccbbbbdec\n", "10"],
        ["caedbdedda\n", "1 9"],
    ],
    117: [
        ["2 1 5 6 2 3\n", "10"],
        ["2 4\n", "4"],
        ["6 2 5 4 5 1 6\n", "12"],
    ],
    118: [
        ["4 5 2 25\n", "5 25 25 -1"],
        ["13 7 6 12\n", "-1 12 12 -1"],
        ["1 2 3 4\n", "2 3 4 -1"],
    ],
    119: [
        ["ADOBECODEBANC\nABC\n", "BANC"],
        ["a\nb\n", ""],
        ["aa\naa\n", "aa"],
    ],
    120: [
        ["1 2 3 null 5 null 4\n", "1 3 4"],
        ["1 2 3 4\n", "1 3 4"],
        ["1 null 2\n", "1 2"],
    ],
    121: [
        ["0 1 0\n0 0 1\n1 1 1\n0 0 0\n", "0 0 0\n1 0 1\n0 1 1\n0 1 0"],
        ["1 1\n1 1\n", "1 1\n1 1"],
        ["1\n", "0"],
    ],
    122: [
        ["2\n1 2\n3 5\n2 4\n", "1 5"],
        ["3\n1 3\n6 9\n11 13\n7 12\n", "1 3\n6 13"],
        ["1\n1 5\n2 3\n", "1 5"],
    ],
    123: [
        ["1 0 1 0 0\n1 0 1 1 1\n1 1 1 1 1\n1 0 0 1 0\n", "6"],
        ["0 1\n1 0\n", "1"],
        ["1\n", "1"],
    ],
    124: [
        ["add 1\nadd 2\nfindMedian\nadd 3\nfindMedian\n", "1.5\n2"],
        ["add 5\nfindMedian\nadd 2\nfindMedian\nadd 4\nfindMedian\n", "5\n3.5\n4"],
        ["add -1\nfindMedian\nadd -2\nfindMedian\n", "-1\n-1.5"],
    ],
    125: [
        ["0 30\n5 10\n15 20\n", "2"],
        ["7 10\n2 4\n", "1"],
        ["0 5\n1 3\n2 6\n", "3"],
    ],
    126: [
        ["1 2\n2 3\n3 4\n1 3\n", "1"],
        ["1 2\n1 2\n1 2\n", "2"],
        ["1 2\n2 3\n", "0"],
    ],
    127: [
        ["oaan\netic\nehts\nhaee\noath pea eat rain\n", "eat\noath"],
        ["a\nb\n", ""],
        ["ab\ncd\na b c d\n", "a\nb\nc\nd"],
    ],
    128: [
        ["5 10 -5\n", "5 10"],
        ["8 -8\n", ""],
        ["10 2 -5\n", "10"],
    ],
    129: [
        ["lee(t(c)o)de)\n", "lee(t(c)o)de"],
        ["a)b(c)d\n", "ab(c)d"],
        ["))((\n", ""],
    ],
    130: [
        ["4 3 2 7 8 2 3 1\n", "2 3"],
        ["1 1 2\n", "1"],
        ["1\n", ""],
    ],
    131: [
        ["1 2 3 6 2 3 4 7 8\n3\n", "true"],
        ["1 2 3 4 5\n4\n", "false"],
        ["1 2 3\n1\n", "true"],
    ],
    132: [
        ["aab\n", "aba"],
        ["aaab\n", ""],
        ["vvvlo\n", "vovlv"],
    ],
    133: [
        ["3\n0 1\n1 2\n", "0 1 2"],
        ["4\n0 1\n1 2\n2 3\n", "0 1 2 3"],
        ["2\n0 1\n", "0 1"],
    ],
    134: [
        [
            "insert apple\ninsert apple\ncountWordsEqualTo apple\ncountWordsStartingWith app\nerase apple\ncountWordsEqualTo apple\ncountWordsStartingWith app\n",
            "2\n2\n1\n1",
        ],
        [
            "insert hello\ninsert world\ncountWordsStartingWith wor\ncountWordsEqualTo world\n",
            "1\n1",
        ],
        ["countWordsStartingWith a\ninsert a\ncountWordsEqualTo a\n", "0\n1"],
    ],
    135: [
        [
            "addWord bad\naddWord dad\naddWord mad\nsearch pad\nsearch .ad\nsearch b..\n",
            "false\ntrue\ntrue",
        ],
        ["addWord a\nsearch .\nsearch a\nsearch ..\n", "true\ntrue\nfalse"],
        ["search .a\naddWord aa\nsearch .a\n", "false\ntrue"],
    ],
    136: [
        ["0 1 0 2 1 0 1 3 2 1 2 1\n", "6"],
        ["4 2 0 3 2 5\n", "9"],
        ["4 2 3\n", "1"],
    ],
    137: [
        ["1 3\n2\n", "2"],
        ["1 2\n3 4\n", "2.5"],
        ["0 0\n0 0\n", "0"],
    ],
    138: [
        ["aa\na\n", "false"],
        ["aa\na*\n", "true"],
        ["ab\n.*\n", "true"],
    ],
    139: [
        ["aa\na\n", "false"],
        ["aa\n*\n", "true"],
        ["cb\n?b\n", "true"],
    ],
    140: [
        ["(()\n", "2"],
        [")()())\n", "4"],
        ["()(()\n", "2"],
    ],
    141: [
        [
            "53..7....\n6..195...\n.98....6.\n8...6...3\n4..8.3..1\n7...2...6\n.6....28.\n...419..5\n....8..79\n",
            "534678912\n672195348\n198342567\n859761423\n426853791\n713924856\n961537284\n287419635\n345286179",
        ],
        [
            "..9748...\n7........\n.2.1.9...\n..7...24.\n.64.1.59.\n.98...3..\n...8.3.2.\n........6\n...2759..\n",
            "519748632\n783652419\n426139875\n357986241\n264317598\n198524367\n975863124\n832491756\n641275983",
        ],
        [
            "..594..27\n..7..18..\n2........\n31.4....8\n5......6.\n.2...5..9\n69......5\n.3..269.1\n..1...24.\n",
            "185943627\n947261853\n263857194\n316492578\n579318462\n428675319\n692184735\n734526981\n851739246",
        ],
    ],
    142: [
        ["4\n", ".Q..\n...Q\nQ...\n..Q.\n\n..Q.\nQ...\n...Q\n.Q.."],
        ["1\n", "Q"],
        ["2\n", ""],
    ],
    143: [
        ["hit\ncog\nhot dot dog lot log cog\n", "5"],
        ["hit\ncog\nhot dot dog lot log\n", "0"],
        ["a\nc\na b c\n", "2"],
    ],
    144: [
        ["3 1 5 8\n", "167"],
        ["1 5\n", "10"],
        ["9\n", "9"],
    ],
    145: [
        [
            "push 5\npush 7\npush 5\npush 7\npush 4\npush 5\npop\npop\npop\npop\n",
            "5\n7\n5\n4",
        ],
        ["push 1\npush 1\npop\npop\n", "1\n1"],
        ["push 2\npush 3\npush 3\npop\npop\npop\n", "3\n3\n2"],
    ],
    146: [
        ["set 0 5\nsnap\nset 0 6\nget 0 0\nget 0 1\n", "5\n6"],
        ["snap\nset 1 10\nget 1 0\nget 1 1\n", "0\n10"],
        ["set 0 1\nset 0 2\nsnap\nget 0 0\nsnap\nget 0 1\nget 0 2\n", "2\n2\n2"],
    ],
    147: [
        ["5 2 6 1\n", "2 1 1 0"],
        ["-1 -1\n", "0 0"],
        ["1 2 3 4\n", "0 0 0 0"],
    ],
    148: [
        ["1 3 2 3 1\n", "2"],
        ["2 4 3 5 1\n", "3"],
        ["1\n", "0"],
    ],
    149: [
        ["3\n1 4 5\n1 3 4\n2 6\n", "1 1 2 3 4 4 5 6"],
        ["2\n1 2\n3 4\n", "1 2 3 4"],
        ["1\n5\n", "5"],
    ],
    150: [
        ["2 0\n1 2 3\n0 1 1\n", "4"],
        ["3 0\n1 2 3\n0 1 2\n", "6"],
        ["1 2\n1 2 3\n0 0 0\n", "5"],
    ],
    151: [
        ["4\n0 1\n1 2\n2 0\n1 3\n", "1 3"],
        ["6\n0 1\n1 2\n2 3\n3 0\n2 4\n4 5\n5 2\n", "2 4"],
        ["2\n0 1\n", "0 1"],
    ],
    152: [
        ["5 4\n6 4\n6 7\n2 3\n", "3"],
        ["1 1\n1 1\n1 1\n", "1"],
        ["1 2\n2 3\n3 4\n4 5\n", "4"],
    ],
    153: [
        ["rabbbit\nrabbit\n", "3"],
        ["babgbag\nbag\n", "5"],
        ["abc\nabc\n", "1"],
    ],
    154: [
        ["aabcc\ndbbca\naadbbcbcac\n", "true"],
        ["aabcc\ndbbca\naadbbbaccc\n", "false"],
        ["a\nb\nab\n", "true"],
    ],
    155: [
        ["great\nrgeat\n", "true"],
        ["abcde\ncaebd\n", "false"],
        ["ab\nba\n", "true"],
    ],
    156: [
        ["catsanddog\ncat cats and sand dog\n", "cat sand dog\ncats and dog"],
        [
            "pineapplepenapple\napple pen applepen pine pineapple\n",
            "pine apple pen apple\npine applepen apple\npineapple pen apple",
        ],
        ["catsandog\ncats dog sand and cat\n", ""],
    ],
    157: [
        ["1 2 1 2 3\n2\n", "7"],
        ["1 2 1 3 4\n3\n", "3"],
        ["1 1 1\n1\n", "6"],
    ],
    158: [
        ["1 2 1 2 6 7 5 1\n2\n", "0 3 5"],
        ["4 3 2 1\n1\n", "0 1 2"],
        ["1 1 1 1 1 1\n2\n", "0 2 4"],
    ],
    159: [
        ["0 1 3 5 6 8 12 17\n", "true"],
        ["0 1 2 3 4 8 9 11\n", "false"],
        ["0 1\n", "true"],
    ],
    160: [
        ["1 5 2\n", "false"],
        ["1 5 233 7\n", "true"],
        ["1 1\n", "true"],
    ],
    161: [
        ["3\n1 2 0\n", "3"],
        ["4\n1 2 0 2\n", "3"],
        ["2\n-1 -1\n", "-1"],
    ],
    162: [
        ["3\n0 1 100\n1 2 100\n0 2 500\n0 2 1\n", "200"],
        ["3\n0 1 100\n1 2 100\n0 2 500\n0 2 0\n", "500"],
        ["4\n0 1 100\n1 2 100\n2 3 100\n0 2 500\n0 3 1\n0 3 1\n", "1"],
    ],
    163: [
        ["4\n2 1 1\n2 3 1\n3 4 1\n2\n", "2"],
        ["2\n1 2 1\n1\n", "1"],
        ["2\n1 2 1\n2\n", "-1"],
    ],
    164: [
        ["0 2\n1 3\n", "3"],
        ["0 1 2 3 4\n24 23 22 21 5\n12 13 14 15 16\n11 17 18 19 20\n10 9 8 7 6\n", "16"],
        ["0 1\n2 0\n", "1"],
    ],
    165: [
        ["0 1\n1 0\n", "2"],
        ["0 0 0\n1 1 0\n1 1 0\n", "4"],
        ["1 0\n0 0\n", "-1"],
    ],
    166: [
        [
            "hit\ncog\nhot dot dog lot log cog\n",
            "hit hot dot dog cog\nhit hot lot log cog",
        ],
        ["red\nlex\nted tex tax tad lex\n", "red ted tex lex"],
        ["a\nc\na b c\n", "a c"],
    ],
    167: [
        ["4\n1 2\n3\n3\n-\n", "0 1 3\n0 2 3"],
        ["3\n1\n2\n-\n", "0 1 2"],
        ["2\n1\n-\n", "0 1"],
    ],
    168: [
        ["abcd dcba lls s sssu\n", "0 1\n1 0\n3 2"],
        ["bat tab cat\n", "0 1\n1 0"],
        ["a\n", ""],
    ],
    169: [
        ["123\n", "One Hundred Twenty Three"],
        ["1234567\n", "One Million Two Hundred Thirty Four Thousand Five Hundred Sixty Seven"],
        ["100\n", "One Hundred"],
    ],
    170: [
        ["()())()\n", "(())()\n()()()"],
        ["(a)())()\n", "(a())()\n(a)()()"],
        ["))(\n", ""],
    ],
    171: [
        ["1 0 2\n", "5"],
        ["1 2 2\n", "4"],
        ["1 2 87 87 87 2 1\n", "13"],
    ],
    172: [
        [
            "2\nput 1 1\nput 2 2\nget 1\nput 3 3\nget 2\nget 3\nput 4 4\nget 1\nget 3\nget 4\n",
            "1\n-1\n3\n-1\n3\n4",
        ],
        ["1\nput 1 1\nget 1\nput 2 2\nget 1\nget 2\n", "1\n-1\n2"],
        ["3\nput 1 1\nput 2 2\nput 3 3\nget 1\nget 2\nput 4 4\nget 3\nget 4\n", "1\n2\n-1\n4"],
    ],
    173: [
        ["push 10\npush 5\ngetMin\npush 8\ngetMin\npop\ngetMin\n", "5\n5\n5"],
        ["push 2\npush 0\ngetMin\npush 3\ngetMin\npop\ngetMin\n", "0\n0\n2"],
        ["push 5\ngetMin\npush 5\ngetMin\npop\ngetMin\n", "5\n5\n5"],
    ],
    174: [
        ["1\n", "0"],
        ["5\n", "0"],
        ["100\n", "0"],
    ],
    175: [
        [
            "5 5\n3 0 1 4 2\n5 6 3 2 1\n1 2 0 1 5\n4 1 0 1 7\n1 0 3 0 5\nsum 2 1 4 3\nupdate 3 2 2\nsum 2 1 4 3\n",
            "8\n10",
        ],
        ["2 2\n1 2\n3 4\nsum 0 0 1 1\nupdate 1 1 10\nsum 0 0 1 1\n", "10\n16"],
        ["1 1\n5\nsum 0 0 0 0\nupdate 0 0 7\nsum 0 0 0 0\n", "5\n7"],
    ],
    176: [
        ["5\nadd 0 3\nadd 1 5\nsum 1\nsum 2\nadd 2 2\nsum 2\n", "8\n8\n10"],
        ["3\nadd 0 1\nadd 2 4\nsum 2\nsum 0\n", "5\n1"],
        ["4\nadd 1 2\nadd 3 3\nsum 3\nsum 2\n", "5\n2"],
    ],
    177: [
        ["5\n1 2 3 4 5\nquery 0 4\nupdate 2 10\nquery 0 4\nquery 1 3\n", "15\n22\n16"],
        ["3\n1 1 1\nquery 0 2\nupdate 0 5\nquery 0 2\n", "3\n7"],
        ["1\n7\nquery 0 0\nupdate 0 3\nquery 0 0\n", "7\n3"],
    ],
    178: [
        ["add 1\nadd 2\nadd 3\nfindMedian\nadd 4\nfindMedian\n", "2\n2.5"],
        ["add -3\nfindMedian\nadd -2\nfindMedian\nadd -1\nfindMedian\n", "-3\n-2.5\n-2"],
        ["add 10\nadd 20\nfindMedian\nadd 30\nfindMedian\n", "15\n20"],
    ],
    179: [
        ["1\n0 10\n1\n0 5\n3\n", "10 13"],
        ["1\n5 10\n1\n5 10\n3\n", "0 3"],
        ["2\n10 50\n60 120\n2\n0 15\n60 70\n8\n", "50 58"],
    ],
    180: [
        ["2\n2 4\n1 1\n", "8"],
        ["2\n3 4\n1 1\n", "8"],
        ["2\n10 5\n2 1\n", "15"],
    ],
    181: [
        ["1 7 11\n2 4 6\n3\n", "1 2\n1 4\n1 6"],
        ["1 1 2\n1 2 3\n2\n", "1 1\n1 1"],
        ["1 2\n3\n3\n", "1 3\n2 3"],
    ],
    182: [
        ["1 5 9\n10 11 13\n12 13 15\n8\n", "13"],
        ["1 2\n3 4\n1\n", "1"],
        ["1 2\n3 4\n3\n", "3"],
    ],
    183: [
        ["3\n4 10 15 24 26\n0 9 12 20\n5 18 22 30\n", "20 24"],
        ["2\n1 2 3\n1 2 3\n", "1 1"],
        ["2\n4 10\n3 11\n", "3 4"],
    ],
    184: [
        ["with example science\nthehat\n", "3"],
        ["notice possible\nbasicbasic\n", "-1"],
        ["a b\na\n", "1"],
    ],
    185: [
        ["ghiabcdefhelloadamhelloabcdefghi\n", "7"],
        ["merchant\n", "1"],
        ["aaa\n", "3"],
    ],
    186: [
        ["1 2\n1 2\n2\n", "1 1\n1 2"],
        ["1 1 1\n1 1\n3\n", "1 1\n1 1\n1 1"],
        ["1\n2\n1\n", "1 2"],
    ],
    187: [
        ["0 1 0\n1\n", "2"],
        ["1 1 0\n2\n", "-1"],
        ["0 0 0 1 0 1 1 0\n3\n", "3"],
    ],
    188: [
        ["3 2\n", "3"],
        ["5 5\n", "1"],
        ["4 3\n", "6"],
    ],
    189: [
        ["3\n0 1 0.5\n1 2 0.5\n0 2 0.2\n0 2\n", "0.25"],
        ["3\n0 1 0.5\n1 2 0.5\n0 2 0.3\n0 2\n", "0.3"],
        ["3\n0 1 0.9\n0 2\n", "0"],
    ],
    190: [
        ["0 1 1\n1 1 0\n1 1 0\n", "2"],
        ["0 1 1 0\n", "2"],
        ["0\n", "0"],
    ],
    191: [
        ["3\n1 3\n2 3\n", "2"],
        ["3\n1 2\n2 3\n3 1\n", "-1"],
        ["5\n1 5\n2 5\n3 5\n4 5\n", "2"],
    ],
    192: [
        ["4 2\n2 1\n3 1\n4 1\n", "3"],
        ["4 2\n", "2"],
        ["5 3\n2 1\n3 1\n4 1\n5 1\n", "3"],
    ],
    193: [
        ["0 0 1\n0 0 0\n0 0 0\n", "2"],
        ["1 1\n1 1\n", "0"],
        ["0 1 0\n0 0 0\n", "1"],
    ],
    194: [
        ["1 2 3\n", "0"],
        ["3 2 1\n", "3"],
        ["2 1 3\n", "1"],
    ],
    195: [
        ["1 2 3\n6 5\n", "0"],
        ["12\n4\n", "4"],
        ["1 2\n3 4\n", "3"],
    ],
    196: [
        ["1 2 3 1\n3\n", "5"],
        ["2 5\n4\n", "1"],
        ["1 2 3\n7\n", "0"],
    ],
}
