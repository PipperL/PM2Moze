from copy import deepcopy
from datetime import datetime
# from datetime import timedelta

import click
import numpy as np
import pandas as pd
import re


# pd.options.mode.chained_assignment = None

OPTION_LISTS_TRANSLATION = True


# PM file (exported)
#### TODO: 說明如何匯出檔案

DEFAULT_PM_FILENAME = r"PocketMoney.csv"
DEFAULT_MOZE_FILENAME = r"MOZE.csv"
DEFAULT_PM_LISTS_TRANSLATED = r'PM_all_lists.translated.xlsx'
DEFAULT_PM_ALL_LISTS = r'PM_all_lists.xlsx'

DEBUG_PM_FILENAME_EXCEL = r"DEBUG_PocketMoney.xlsx"
DEBUG_MOZE_FILENAME_EXCEL = r"DEBUG_Moze.xlsx"
DEBUG_PM_DETERMINE_RECORD_TYPE_EXCEL = r"DEBUG_PM_DETERMINE_RECORD_TYPE_EXCEL.xlsx"
DEBUG_PM_FIX_TRANSFER_BEFORE_EXCEL = r"DEBUG_PM_FIX_TRANSFER_BEFORE_EXCEL.xlsx"
DEBUG_PM_FIX_TRANSFER_AFTER_EXCEL = r"DEBUG_PM_FIX_TRANSFER_AFTER_EXCEL.xlsx"
DEBUG_PM_TRANSLATED_EXCEL = r"DEBUG_PM_TRANSLATED_EXCEL.xlsx"
DEBUG_PM_DETERMINE_CATEGORY_EXCEL = r"DEBUG_PM_DETERMINE_CATEGORY_EXCEL.xlsx"
DEBUG_MOZE_MAPPED = r"DEBUG_MOZE_MAPPED.xlsx"
DEBUG_TMP_EXCEL = r"DEBUG_TMP.xlsx"

DEBUG_mode=False


MOZE_HEADER = [
    # Required
    "帳戶",
    "幣種",
    # Required
    "記錄類型",
    "主類別",
    "子類別",
    "金額",
    "手續費",
    "折扣",
    "名稱",
    "商家",
    "日期",
    "時間",
    "專案",
    "描述",
    "標籤",
    "對象",
]
# mapping regular cols
# from PM2 : MOZE
COL_MAPPING_TABLE = {
    'Account':'帳戶',
    'CurrencyCode':'幣種',
    '記錄類型':'記錄類型',        
    'Category_Main':'主類別',        
    'Category_Sub':'子類別',        
    'Amount':'金額',        
    '手續費':'手續費',        
    '折扣':'折扣',             
    'Payee':'商家',            
    'Class':'專案', 
    'Date_f':'日期',
    'Time_f':'時間',
    'Memo':'描述'        
}



def load_pm2_csvfile(input_file):
  
    try:
        # print(input_file)
        # df = pd.read_csv(DEFAULT_PM_FILENAME, skiprows=0,thousands=',')        
        df = pd.read_csv(input_file, skiprows=0,thousands=',')

        if DEBUG_mode:
            df.to_excel(DEBUG_PM_FILENAME_EXCEL,engine='xlsxwriter',index=False)

        return df
    except :
        print(f"Error Loading input_file: {input_file}\nexit...")
        return pd.DataFrame()
    

def determine_record_type(df):

    # determine record type (記錄類型)
    # 判斷記錄類型為支出/收入/轉出/轉入 (PM無 應收款項 / 應付款項 / 餘額調整 / 退款)
    # 先用金額正/負來判斷支出/收入，但可能造成同一類別名稱出現在收入與支出
    # MOZE 支出/收入可以有同名的類別，但是無法像PM一樣支出類別為正數 (或收入類別為負數)
    # 所以碰到像現金回饋(收入)要歸到交易手續費(支出)就麻煩了...
    # 要先想好怎麼轉…
    # 在moze app裡是用"折扣 & 手續費"來處理 
    # ex: 手續費回饋，支出 金額=0，折扣=50
    # ex2: 退費，支出 金額=0，折扣=680
    # 如何判斷 PM 的帳戶類型？ PM的帳戶無收入/支出帳戶的概念，而是用金額正負來顯示金流
    # 方法1: 統計交易次數，負的居多則定義為支出
    # 方法2：統計交易金額累計正負，若以負的居多則定義為支出

    # 先使用方法2    
    tmp = df.loc[:,['Category','Amount']].groupby('Category').sum()
    # print(tmp)

    # save expense list for comparison
    category_type_expense = tmp[tmp['Amount']<0]
    expense_list = []
    for cat in category_type_expense['Amount'].index:
        expense_list.append(cat)

    df['is_expense'] = df['Category'].isin(expense_list)

    # DIRTY: There is a bug in my exported csv, don't know why
    # a lot "<0 Cash>" records in payee become "0 Cash" after exported
    # Need manually modification
    # df.loc[df['Payee']==r'0 Cash','Payee']= r'<' + df['Payee'] + r'>'
    
    # find transfer in and out using Payee   
    df['is_transfer_in'] = df['Payee'].str.startswith('<') & df['Payee'].str.endswith('>') & df['Amount'].ge(0)
    df['is_transfer_out'] = df['Payee'].str.startswith('<') & df['Payee'].str.endswith('>') & df['Amount'].lt(0)
    df['is_expense'] = df['is_expense'] & ~df['is_transfer_in'] & ~df['is_transfer_out']
    df['is_income'] = ~df['is_expense'] & ~df['is_transfer_in'] & ~df['is_transfer_out']

    # write record_type string
    df.loc[df['is_expense']==True, "記錄類型"] ="支出"
    df.loc[df['is_income']==True, "記錄類型"] ="收入"
    df.loc[df['is_transfer_in']==True, "記錄類型"] ="轉入"
    df.loc[df['is_transfer_out']==True, "記錄類型"] ="轉出"

    if DEBUG_mode:
        df.to_excel(DEBUG_PM_DETERMINE_RECORD_TYPE_EXCEL,engine='xlsxwriter',index=False) 

 

def fix_transfer_missing(df):

    # CAUTION: Resources consuming !!!

    # PM2 若對某個帳戶作「匯總」，
    # 雖然收入/支出會被匯總，但是轉帳資訊會變成不對稱(剩一筆)
    # 所以需要回溯去把對稱的轉帳紀錄加回去，但金額為0
    # 才能匯入又不影響總數
    # 又因為轉帳對稱需上下相鄰，用 sort 方式還是沒辦法把所有的狀況考慮進去
    # 所以轉入/轉出 改用較髒的作法，從資料庫中抓出來逐筆檢查配對，加上獨一標記，最後再倒回去

    df['is_Xfer'] = df['is_transfer_in'] | df['is_transfer_out']
    # xfer_df = df[df['is_Xfer']==True]
    xfer_df = df[df['is_Xfer']==True].copy()
    non_xfer_df = df[df['is_Xfer']==False].copy()

    # get payee for comparison
    xfer_df['Payee'] = xfer_df['Payee'].str.strip('>')
    xfer_df['Payee'] = xfer_df['Payee'].str.strip('<')

    # 不排序好像有點問題，還是排一下好了
    xfer_df['Amount_abs'] = xfer_df['Amount'].abs()  # 金額不一定準，因為有跨幣種轉帳的問題
    # 產生 (Account_from)_(Accout_to) 用來比對
    ap_gen1 = lambda s1, s2: str(s1) + '-' + str(s2)
    ap_gen2 = lambda s1, s2: str(s2) + '-' + str(s1)

    xfer_df.loc[xfer_df['is_transfer_out']==True,'Account_pair'] = xfer_df['Account'].combine(xfer_df['Payee'],ap_gen1 )
    xfer_df.loc[xfer_df['is_transfer_in']==True,'Account_pair'] = xfer_df['Account'].combine(xfer_df['Payee'],ap_gen2 )
    xfer_df.sort_values(by=['Date', 'Memo', 'Account_pair', 'Amount_abs'], inplace=True)
    xfer_df.reset_index(inplace=True)
    # xfer_df.sort_values(by=['pair_serial']).to_excel(DEBUG_TMP_EXCEL,engine='xlsxwriter')

    # 逐行掃過，找出落單的，加上一行對應的轉出入 (現金，金額為零)
    # 並將配對好的，加上flag
       
    xfer_df['is_paired'] = False
    xfer_df['pair_serial'] = np.nan
    xfer_df['pair_type']= 0     # 1=轉出 2=轉入
    xfer_df['is_initially_broken']= False    # flag those initially not paired.
    
    if DEBUG_mode:
        xfer_df.to_excel(DEBUG_PM_FIX_TRANSFER_BEFORE_EXCEL,engine='xlsxwriter',index=False)

    tmp_lists=pd.DataFrame()

    pre1_id = -1
    cur_id  = -1
    pair_serial = 1
    
    
    for cur_id in xfer_df.index:
        
        if pre1_id==-1: 
            # 1st row case
            # pass
            pre1_id = cur_id
            continue
            
        if xfer_df['is_paired'][pre1_id]==True:
            # if have been paired, pass
            pre1_id = cur_id
            continue            
        
        chk1 = (xfer_df.loc[pre1_id,'is_transfer_in'] == True) & (xfer_df.loc[cur_id,'is_transfer_out'] == True)
        chk2 = (xfer_df.loc[pre1_id,'is_transfer_out'] == True) & (xfer_df.loc[cur_id,'is_transfer_in'] == True)
        chk3 = xfer_df.loc[pre1_id,'Date']== xfer_df.loc[cur_id,'Date']
        chk4 = (xfer_df.loc[pre1_id,'Amount'] * xfer_df.loc[cur_id,'Amount']) < 0  # 金額可能受幣值影響不準，僅正負號可參考
        chk5A = (xfer_df.loc[pre1_id,'Memo'] is np.nan) & (xfer_df.loc[cur_id,'Memo'] is np.nan)
        chk5B = xfer_df.loc[pre1_id,'Memo']== xfer_df.loc[cur_id,'Memo'] # Careful NaN != NaN if NaN or null, can not compare!
        chk5 = chk5A | chk5B
        chk6 = (xfer_df.loc[pre1_id,'Account']== xfer_df.loc[cur_id,'Payee']) & (xfer_df.loc[cur_id,'Account']== xfer_df.loc[pre1_id,'Payee'])
    

        if (chk1|chk2) & chk3 & chk4 & chk5 & chk6 :
            # 轉入轉出配成組Paired
            # print(str(cur_id) + ' paired! ' + pre_datetime_str + 'vs' + cur_datetime_str)
            # 同一組的紀錄不用改時間，用 pair_serial 寫入未來排序即可
            
            xfer_df.loc[[pre1_id,cur_id],'is_paired']= True                    
            xfer_df.loc[[pre1_id, cur_id],'pair_serial']= pair_serial
            # xfer_df.loc[pre1_id,'pair_serial']= pair_serial            
            pair_serial = pair_serial + 1

            # if chk2==True:
            #     xfer_df.loc[pre1_id,'pair_type'] = 1
            #     xfer_df.loc[cur_id,'pair_type'] = 2                
            # else:
            #     xfer_df.loc[pre1_id,'pair_type'] = 2
            #     xfer_df.loc[cur_id,'pair_type'] = 1

        else :

            # pre1 not paired, add new row for it
            tmp_row = xfer_df.xs(pre1_id, drop_level=False).copy()
           
            xfer_df.loc[pre1_id,'is_paired']= True
            tmp_row['is_paired']= True
            xfer_df.loc[pre1_id,'is_initially_broken']= True
            tmp_row['is_initially_broken']= True
            xfer_df.loc[pre1_id,'pair_serial']= pair_serial
            tmp_row['pair_serial']= pair_serial
            pair_serial = pair_serial + 1           

            tmp_row['Account'] = xfer_df.loc[pre1_id,'Payee']
            tmp_row['Payee'] = xfer_df.loc[pre1_id,'Account'] 
            tmp_row['Amount'] = 0
            tmp_lists = pd.concat([tmp_lists,tmp_row],axis=1) 
           

        # Iterate!    
        pre1_id = cur_id

    # reverse xfer_df_fix [is_transfer_in ... 記錄類型]
    xfer_df_fix = tmp_lists.T
    if xfer_df_fix.size > 0 :  
        xfer_df_fix['is_transfer_in'] = ~ xfer_df_fix['is_transfer_in']
        xfer_df_fix['is_transfer_out'] = ~ xfer_df_fix['is_transfer_out']
        xfer_df_fix.loc[xfer_df_fix['is_transfer_in']==True, "記錄類型"] ="轉入"
        xfer_df_fix.loc[xfer_df_fix['is_transfer_out']==True, "記錄類型"] ="轉出"
        xfer_df = xfer_df.append(xfer_df_fix, sort=False)

    # remove Payee for is_transfer type record
    xfer_df.loc[xfer_df['is_transfer_in']==True, ["Payee",'pair_type']] =['',2] # 轉入
    xfer_df.loc[xfer_df['is_transfer_out']==True, ["Payee",'pair_type']] =['',1] # 轉出
    


    # 跨幣種轉帳時，PM2轉出轉入的幣種跟MOZE是相反的
    # 所以針對跨幣種轉帳 再處理一次
    # 前提的處理手段：必須已經成對且排好序，不然容易亂掉
    # 
    # PM2匯率的處理也很亂。    
    # case 1: <wrong>支出時 Amount 就是該幣種的票面數字 ex: $399 USD => 不用改 </wrong>
    # case 1: 支出時 Amount 是等效台幣的數字，所以要先用匯率換算回去該幣種的實際數字
    # case 2: 轉帳時 Amount 是等效台幣的數字，所以要先用匯率換算回去該幣種的實際數字
    # case 3: 轉帳時 轉進轉出的幣種是相反的，所以必須對調。但對調時幣除了幣種之外，對應的數字也要跟著對調，還要修正正負號...
    # case 4: 若一開始沒有成對的紀錄 (後來補0的)，則必須避開，不對調金額
    # case 5: 若兩者幣種相同，仍然要依匯率換算，但不要對調金額
    
    # for PM2 the Amount(NTD) = CurrencyCode (USD) * ExchangeRate
    # for Moze the Amount is base on CurrencyCode
    # So in PM2 will be Amount=10000 (NTD), CurrencyCode=USD, ExchangeRate=30.09
    # in Moze should be Amount=3323.36 (USD), CurrencyCode=USD
    # df['Amount']= df['Amount'] / df['ExchangeRate']
    
    
    xfer_df_out = xfer_df.loc[xfer_df['is_transfer_out']==True].sort_values(by=['pair_serial']).reset_index(drop=True)
    xfer_df_in = xfer_df.loc[xfer_df['is_transfer_in']==True].sort_values(by=['pair_serial']).reset_index(drop=True)
    
    if xfer_df_out.size != xfer_df_in.size:
        print('WARNING! Size of xfer_df_out and xfer_df_in is different')

    # xfer_df_out.to_excel(DEBUG_TMP_EXCEL+'_out.xlsx',engine='xlsxwriter')
    # xfer_df_in.to_excel(DEBUG_TMP_EXCEL+'_in.xlsx',engine='xlsxwriter')

    # calculate real amount according ExchangeRate
    xfer_df_out['Amount']= xfer_df_out['Amount'] / xfer_df_out['ExchangeRate']
    xfer_df_in['Amount']= xfer_df_in['Amount'] / xfer_df_in['ExchangeRate']

    # SWAP currencycode
    tmp_col = xfer_df_out['CurrencyCode'].copy()
    xfer_df_out['CurrencyCode'] = xfer_df_in['CurrencyCode'].copy()
    xfer_df_in['CurrencyCode'] = tmp_col.copy()
    
    # SWAP amount, except those ['CurrencyCode'] is the same
    tmp_col2 = xfer_df_out['Amount'].where(xfer_df_out['CurrencyCode']==xfer_df_in['CurrencyCode'], xfer_df_in['Amount']  * -1 )
    tmp_col = xfer_df_in['Amount'].where(xfer_df_out['CurrencyCode']==xfer_df_in['CurrencyCode'], xfer_df_out['Amount']  * -1 )
    xfer_df_out['Amount'] = tmp_col2.copy() 
    xfer_df_in['Amount'] = tmp_col.copy()

    # xfer_df_out.to_excel(DEBUG_TMP_EXCEL+'_out2.xlsx',engine='xlsxwriter')
    # xfer_df_in.to_excel(DEBUG_TMP_EXCEL+'_in2.xlsx',engine='xlsxwriter')

    xfer_df = xfer_df_out.append(xfer_df_in, sort=False)

    # xfer_df_db = xfer_df.sort_values(by=['pair_serial'])
    # xfer_df_db.to_excel(DEBUG_TMP_EXCEL,engine='xlsxwriter')

    # dear w/ amount for non-xfer
    non_xfer_df['Amount']= non_xfer_df['Amount'] / non_xfer_df['ExchangeRate']

    # Combine xfer and non_xfer
    df2 = non_xfer_df.append(xfer_df,sort=False)

    # Sorting:
    df2.sort_values(by=['Date','pair_serial','pair_type'], inplace=True)
    df2.reset_index(inplace=True,drop=True)

    if DEBUG_mode:
        df2.to_excel(DEBUG_PM_FIX_TRANSFER_AFTER_EXCEL,engine='xlsxwriter',index=False)

    return df2


def get_pm_all_lists(df):
    # get pm all list and save to an excel for further category translation
    # disabled by default

    df_lists = pd.DataFrame(columns=['PM_Category','Moze_Category','PM_Account','Moze_Account','PM_Payee','Moze_Payee'])
    # df_lists = pd.DataFrame()
     
    tmp_df = df
    tmp1= tmp_df['Category'].drop_duplicates().sort_values().reset_index(drop=True)
    tmp_df = df
    tmp2 = tmp_df['Account'].drop_duplicates().sort_values().reset_index(drop=True)
    tmp_df = df

    # Payee: Remove Transfer accounts in Payee
    tmp_df['is_Payee'] = df['Payee'].str.startswith('<') & df['Payee'].str.endswith('>')
    tmp_df['Payee'] = tmp_df['Payee'].mask(tmp_df['is_Payee'])
    tmp3 = tmp_df['Payee'].drop_duplicates().sort_values().reset_index(drop=True)    
    # print(tmp3)

    tmp_lists = pd.concat([tmp1,tmp2,tmp3],axis=1)   
    # print(tmp_lists)
    df_lists[['PM_Category','PM_Account','PM_Payee']] = tmp_lists[['Category','Account','Payee']]
    # print(df_lists)
    # df_lists.to_excel(DEFAULT_PM_ALL_LISTS,engine='xlsxwriter',index=False)
    return df_lists

    
def determine_category(df):
    # split main and sub category
    # use discount to process positive expense
    # use negative discount to process negative income
    
    # split main and sub category
    splited = df['Category'].str.split(pat=':',n=2,expand=True )
    # print(splited.head(30))

    # write expense category
    df.loc[df['is_expense']==True, "Category_Main"] = splited[0]
    df.loc[df['is_expense']==True, "Category_Sub"] = splited[1]

    # write income category
    df.loc[df['is_income']==True, "Category_Main"] = '收入'
    df.loc[df['is_income']==True, "Category_Sub"] = df['Category']

    # write transfer catefory
    df.loc[df['is_transfer_in']==True, "Category_Main"] = "轉帳"
    df.loc[df['is_transfer_in']==True, "Category_Sub"] = "轉帳"
    df.loc[df['is_transfer_out']==True, "Category_Main"] = "轉帳"
    df.loc[df['is_transfer_out']==True, "Category_Sub"] = "轉帳"

    # avoid sub category is NaN or none
    df.loc[df['Category_Sub'].isna(), "Category_Sub"] = "其他"

    # use discount to process positive expense
    # use negative fee to process negative income
    df['is_positive_expense'] = df['is_expense'] & df['Amount'].gt(0)
    df['is_negative_income'] = df['is_income'] & df['Amount'].lt(0)

    
    df.loc[df['is_positive_expense']==True, "折扣"] = df['Amount']
    df.loc[df['is_positive_expense']==True, "Amount"] = 0
    df.loc[df['is_negative_income']==True, "手續費"] = df['Amount'].mul(-1)
    df.loc[df['is_negative_income']==True, "Amount"] = 0


    # extract date and time 
    df['Date_f'] = df['Date'].apply(
        lambda x: datetime.strptime(str(x), r'%Y年%m月%d日 %H:%M').strftime(r'%Y/%m/%d')
    )

    df['Time_f'] = df['Date'].apply(
        lambda x: datetime.strptime(str(x), r'%Y年%m月%d日 %H:%M').strftime(r'%H:%M')
    )

    if DEBUG_mode:
        df.to_excel(DEBUG_PM_DETERMINE_CATEGORY_EXCEL,engine='xlsxwriter',index=False)    


def translate_lists(df):
    # translate Category_Main and Category_Sub using mapping table
    # for PM2 it is like "1 飲食:1B Lunch"
    # for Moze it will become "飲食:午餐"

    # read mapping file from file (excel)
    #### TODO: test if file is exist
    try:
        map_df = pd.read_excel(DEFAULT_PM_LISTS_TRANSLATED)
    except:
        click.echo(f"ERROR: cannont open {DEFAULT_PM_LISTS_TRANSLATED} for translation")
        return
        
    CAT_MAPPING_TABLE_FROM_FILE={}
    for key,val in map_df['PM_Category'].items():
        # examine input        
        if ~str(val).isspace() & (val is not np.NaN) & (map_df['Moze_Category'][key] is not np.NaN):
            CAT_MAPPING_TABLE_FROM_FILE[str(val)] = str(map_df['Moze_Category'][key])

    CAT_MAPPING_TABLE = CAT_MAPPING_TABLE_FROM_FILE    
    df['Category_Translated'] = df['Category'].apply(
        lambda x: CAT_MAPPING_TABLE.get(x,x)
    )


    ACCOUNT_MAPPING_TABLE_FROM_FILE={}
    for key,val in map_df['PM_Account'].items():
        # examine input        
        if ~str(val).isspace() & (val is not np.NaN) & (map_df['Moze_Account'][key] is not np.NaN):
            ACCOUNT_MAPPING_TABLE_FROM_FILE[str(val)] = str(map_df['Moze_Account'][key])
    
    ACCOUNT_MAPPING_TABLE = ACCOUNT_MAPPING_TABLE_FROM_FILE  
    df['Account_Translated'] = df['Account'].apply(
        lambda x: ACCOUNT_MAPPING_TABLE.get(x,x)
    )


    PAYEE_MAPPING_TABLE_FROM_FILE={}
    for key,val in map_df['PM_Payee'].items():
        # examine input          
        if ~str(val).isspace() & (val is not np.NaN) & (map_df['Moze_Payee'][key] is not np.NaN):
            PAYEE_MAPPING_TABLE_FROM_FILE[str(val)] = str(map_df['Moze_Payee'][key])

    PAYEE_MAPPING_TABLE = PAYEE_MAPPING_TABLE_FROM_FILE    
    df['Payee_Translated'] = df['Payee'].apply(
        lambda x: PAYEE_MAPPING_TABLE.get(x,x)
    )
   
    # overwrite origin columns:
    df['Category'] = df['Category_Translated']
    df['Account'] = df['Account_Translated']
    df['Payee'] = df['Payee_Translated']

def pm2moze_col_mapping(pm_df, moze_df):
    # mapping corresponding columns from pm_df

    # do the sort...
    pm_df.sort_values(by=['Date_f','Time_f','pair_serial','pair_type'], inplace=True)
    pm_df.reset_index(inplace=True, drop=True)

    for pm_col,moze_col in COL_MAPPING_TABLE.items() :
        moze_df[moze_col] = pm_df[pm_col]


    # print(moze_df.tail(30))
    if DEBUG_mode:
        moze_df.to_excel(DEBUG_MOZE_MAPPED,engine='xlsxwriter',index=False)

def final_check_moze_df(moze_df):
    # do some final checks and modifications
    moze_df2 = moze_df[MOZE_HEADER]

    

    return moze_df2


##################################################################################
# Main program
##################################################################################

@click.group()
@click.option("--input_file",'-i', default=DEFAULT_PM_FILENAME, help=f"Input filename from PM2",show_default=True)
@click.option("--output_file",'-o', default=DEFAULT_MOZE_FILENAME, help="Output filename for Moze 3.0",show_default=True)
@click.option("--translation/--no-translation", default=True, help=f"Translation list defined in {DEFAULT_PM_LISTS_TRANSLATED}", show_default=True)
@click.option('--debug', is_flag=True, help="DEBUG mode: writing temp files for debugging (see debug.filename)")
# @click.option("--MOZE_file",'-o', prompt="Your name",help="The person to greet.")
@click.pass_context
def cli(ctx,input_file,output_file, translation, debug ):
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)

    ctx.obj['DEBUG'] = debug
    ctx.obj["input_file"] = input_file
    ctx.obj["output_file"] = output_file

    if translation:
        ctx.obj["TRANSLATION"] = True
    else:
        ctx.obj["TRANSLATION"] = False
    
    global DEBUG_mode
    DEBUG_mode = debug







@cli.command()
@click.pass_context
def list(ctx):
    """Generate lists of Category, Account, and Payee."""
   
    input_file = ctx.obj["input_file"]
    # DEBUG_mode= ctx.obj["DEBUG"]
    
    click.echo(f"Loading lists from input file: {input_file}")
    df = load_pm2_csvfile(input_file)
    if df.empty:
        # click.echo(f'ERROR: List is empty!')
        return
    
    # moze_df = pd.DataFrame(columns=MOZE_HEADER)      

    click.echo(f"Determining record type...")
    determine_record_type(df)
    click.echo(f"Fixing non-paired transfer record...")
    df=fix_transfer_missing(df)
    click.echo(f"Extracting Category, Account, and Payee lists...")
    df_lists = get_pm_all_lists(df)
    click.echo(f"Writing list to {DEFAULT_PM_ALL_LISTS}...")
    try:
        df_lists.to_excel(DEFAULT_PM_ALL_LISTS,engine='xlsxwriter',index=False)
        print(
            f"""\nSUCCESS:
            All Lists are extracted.
            Please find it in {DEFAULT_PM_ALL_LISTS}
            You can now edit it manually, 
            then save it as {DEFAULT_PM_LISTS_TRANSLATED}
            After that, the list will be translated/mapped during convertion"""
        )

    except :
        click.echo(f"\nERROR:\nSomething wrong while writing lists!\nPlease check if file is opened or permission is incorrect.")
        pass

    
    



@cli.command()
@click.pass_context
def convert(ctx):
    """Convert the PM2 csv to Moze csv"""

    input_file = ctx.obj["input_file"]
    output_file = ctx.obj["output_file"]
    OPTION_LISTS_TRANSLATION = ctx.obj["TRANSLATION"]
    # DEBUG_mode= ctx.obj["DEBUG"]
    # print(DEBUG_mode)
    

    click.echo(f"Loading input CSV file: {input_file}")
    df = load_pm2_csvfile(input_file)
    if df.empty:
        # click.echo(f'ERROR: List is empty!')
        return
    
    moze_df = pd.DataFrame(columns=MOZE_HEADER)      

    click.echo(f"Determining record type...")
    determine_record_type(df)
    click.echo(f"Fixing non-paired transfer record...")
    df=fix_transfer_missing(df)

    if OPTION_LISTS_TRANSLATION==True:
        click.echo(f"Reading Translated lists from {DEFAULT_PM_LISTS_TRANSLATED}...")
        translate_lists(df)

    click.echo(f"Processing Categoty, column name, and date format...")
    determine_category(df)
    pm2moze_col_mapping(df,moze_df)

    click.echo(f"Final checking record integrity...")
    moze_df = final_check_moze_df(moze_df)

    click.echo(f"Writing data into {output_file}...")

    try:
        moze_df.to_csv(output_file, index=False)
        click.echo(f"""\nSUCCESS:
            PM2 Records has been converted to Moze format.
            You can now import {output_file} into Moze.
            Please visit moze.app for how to import data.""")

        if DEBUG_mode:
            moze_df.to_excel(DEBUG_MOZE_FILENAME_EXCEL,engine='xlsxwriter',index=False)        

    except :
        # print(f"Error Writing output_file: {output_file}\nexit...")
        click.echo(f"\nERROR:\nSomething wrong while writing output file({output_file})!\nPlease check if file is opened or permission is incorrect.")

        pass

    # df.to_excel(DEFAULT_MOZE_FILENAME_EXCEL,engine='xlsxwriter',index=False)
  
    
    

if __name__ == '__main__':
    cli(obj={})