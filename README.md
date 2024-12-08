# zse
A python program built for UNSW students to submit files and run autotests on local files. Heavily inspired by [cserun](https://cserun.bojin.co/)


## Usage

<pre style="font-family: 'Cascadia Mono', monospace; font-size: 12px;">
<span style="color: lightgreen;">> zse "1511 autotest bad_pun" -d ./tests/</span>
<span style="color: cyan;">[1/5]</span> Connecting to: <span style="color: yellow;">login.cse.unsw.edu.au:22</span>  
<span style="color: cyan;">[2/5]</span> Authenticated as: <span style="color: lightgreen;">z5583960</span>  
<span style="color: cyan;">[3/5]</span> Establishing SFTP connection  
<span style="color: cyan;">[4/5]</span> Synced local files to remote  
<span style="color: cyan;">[5/5]</span> Command sent: <span style="color: lightgreen;">1511 autotest bad_pun</span>
============== Output ==============  
<span style="color: lightblue;">1511 c_check bad_pun.c</span>  
<span style="color: lightblue;">dcc -Werror -o bad_pun bad_pun.c</span>  
Test 0 (./bad_pun) - <span style="color: lightgreen;">passed</span>  
====================================
<span style="color: lightgreen;">1 tests passed</span> <span style="color: red;">0 tests failed</span>  
====================================
Exit Status: <span style="color: lightgreen;">0</span>  
</pre>


## Installation
To get started with `zse`, follow these steps:

1. Install the package using [pip](https://pip.pypa.io/en/stable/):

   ```bash
   pip install zse
   ```



## Task list
- [x] Add Y/n confirmation before fetching from remote
- [ ] Enhance pipe feature i.e. actually make it useful
- [x] Add more to readme.md such as how to create exe and add to system path
