import subprocess
import json

dummy_data = {
        'Housing': [
            {"name": "Rent", "cost": 2800.00, "type": "Monthly"},
            {"name": "Home Insurance", "cost": 1200.00, "type": "Yearly"},
        ],
        'Food': [
            {"name": "Groceries", "cost": 900.00, "type": "Monthly"},
            {"name": "Dining Out", "cost": 250.00, "type": "Monthly"},
        ],
        'Transportation': [
            {"name": "Public Transit Pass", "cost": 150.00, "type": "Monthly"},
            {"name": "Car Insurance", "cost": 2200.00, "type": "Yearly"},
        ],
        'Utilities': [
            {"name": "Electricity", "cost": 320.00, "type": "Monthly"},
            {"name": "Internet", "cost": 120.00, "type": "Monthly"},
        ],
        'Miscellaneous': [
            {"name": "Gym Membership", "cost": 39.90, "type": "Monthly"},
            {"name": "Streaming Services", "cost": 55.00, "type": "Monthly"},
        ],
    }
def expense_menu(expenses):
     """
     Displays the dummy data menu and lets the user choose to replace or append dummy data.

     Args:
         expenses (dict): dictionary containing all the expenses

     Returns:
         None
     """
     CYAN = "\033[36m"
     RESET = "\033[0m"
     while True:
        subprocess.run("cls", shell=True, check=False)  # For Windows
        print("\n\n\n")
        print("=" * 50)
        print(CYAN + "1 - replace data with dummy data")
        print("2 - append dummy data to existing data")
        print("3 - load dummy data from json (OVERWRITE)")
        print("0 - back" + RESET)
        print("=" * 50)
        print("\n")

        # tries to catch exception if the user inputs a wrong
        # type and also if the user interrupted with keyboard (ctrl+c)
        try:
            choice = int(input("Enter Selection "))
        except ValueError:
            input("Please enter a valid number, then press Enter to try again")
            continue
        except KeyboardInterrupt:
            print("\nExiting due to user interrupt...")
            break

        # match case for user menu selection
        match choice:
            case 1:
                print()
                load_dummy_data(expenses)
                

            case 2:
                print()
                load_dummy_data_append(expenses)
            
            case 3:
                print()
                load_from_file(expenses)
            case 0:
                break
            
            case _: 
              input("please select from the menu, then press Enter to try again ")
              continue




def load_dummy_data(expenses): 
    """
    This function loads dummy data into the expenses dict in the main file
    
    Args:
        expenses (dict): dictionary containing all the expenses  
    
    Returns:
        None
    """

    # clears the current expenses dict and writes dummy data to it
    expenses.clear()
    expenses.update(dummy_data)
    input("DUMMY DATA LOADED SUCCESSFULLY, press Enter to continue")

def load_dummy_data_append(expenses):
    """
    Appends dummy data to the existing expenses dict without clearing it.

    Args:
        expenses (dict): dictionary containing all the expenses

    Returns:
        None
    """
    for category, items in dummy_data.items():
        expenses.setdefault(category, []).extend(items)

    input("DUMMY DATA LOADED SUCCESSFULLY (APPENDED), press Enter to continue")

def load_from_file(expenses):
    """
    This function loads a json file to the expenses dict
    
    Args:
        expenses (dict): dictionary containing all the expenses  
    
    Returns:
        None
    """
    # take the filename from the user and strips spaces to avoid mistakes
    filename = input("enter file name to load ").strip()

    # searches for if the file already exist and loads it
    if not filename.endswith(".json"): filename += ".json"
    try:
     with open(filename, "r") as f:
        load = json.load(f)
    except FileNotFoundError:
       input("File Not Found, press any key to return to menu")
       return
    except json.JSONDecodeError:
        input("File is not a valid json, press any key to return to menu")
        return
    
    expenses.clear()
    expenses.update(load)
    input (f"FILE {filename.strip().lower()} LOADED SUCCESSFULLY, ENTER ANY KEY TO CONTINUE")