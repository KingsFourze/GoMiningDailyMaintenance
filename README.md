# GoMining Daily Maintenance
A script to click the maintenance button on GoMining.

## Usage

### First time to use
- Install uv  
Check [here](https://docs.astral.sh/uv/getting-started/installation/) to install `uv`
- Clone this repo
    ```
    git clone https://github.com/KingsFourze/GoMiningDailyMaintenance.git
    ```
- Initialize the virtual environment
    ```
    uv sync
    ```
- Run the `login` mode
    ```
    uv run main.py login
    ```
- Input your account / password / TOTP code
    ```
    # For example
    [INFO] Login form loaded.
    Enter your email: user@example.com                          # input Account
    Enter your password: p@ssw0rd                               # input Password
    [INFO] Login button clicked.
    [INFO] TOTP code inputs loaded.
    Enter your TOTP code: 000000                                # input TOTP
    [INFO] Login successful. Cookies saved to cookies.dat.
    ```

### After login Success
- Run the `maintenance` mode
    ```
    uv run main.py maintenance
    ```
- After the maintenance is success, set it to the cron job / task scheduler

## Thanks to
- [zendriver](https://github.com/cdpdriver/zendriver) contributors