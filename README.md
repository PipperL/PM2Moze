# PM2Moze
A conversion tool for data migration from PocketMoney 2 (PM2) to Moze 3

Pre-requsite:
----

    pip install click 
    pip install pandas
    


Introduction
----
This is my very first python script.
It's a tool for data migration from PocketMoney 2 (PM2) to Moze 3.
It convert PM2 exported file (CSV format) to Moze 3.
Both PM2 and Moze 3 are

這是我第一個 python作品，
主要是協助想要從PockeyMoney 2 (PM2) 跳船 Moze 3的人。
從之前PM2 匯出的資料檔案(csv格式) 可以轉換成Moze 3 的CSV格式。
然後再匯入Moze 3 裡。
PM2跟Moze 3都是 iOS 上的記帳軟體。

Usage:
----
    python PM2Moze.py [OPTIONS] COMMAND

* Options:
  * <code>-i, --input_file TEXT </code> Input filename from PM2  [default:PocketMoney.csv]
  * <code>-o, --output_file TEXT </code> Output filename for Moze 3.0  [default:  MOZE.csv]
  * <code>--translation / --no-translation </code> Translation list defined in   PM_all_lists.translated.xlsx  [default: True]
  * <code>--debug</code> DEBUG mode: writing temp files for debugging (see DEBUG_filename)
  * <code>--help</code> Show this message and exit.

* Commands:
  * <code>convert</code>  Convert the PM2 csv to Moze csv
  * <code>list</code>     Generate lists of Category, Account, and Payee.


教學:
----
**步驟1：匯出PM2的資料**

* 在PM2的主畫面，左下角(分享icon)->Options-> QIF密碼：請設為 Unicode
* 點選主畫面右下角眼睛icon->顯示帳戶 所有帳戶。
* 回到主畫面，下方自訂->所有交易
* 點選下方工具->檔案傳輸->電子郵件->CSV->寄到自己的信箱
* 到你的email inbox裡，把CSV檔下載複製到PM2Moze的目錄下，更名為PocketMoney.csv

**步驟2：製作Translation Table**
* PM2Moze 有個功能，可以讓你在轉換的過程中，把類別、帳戶、跟受款人(Payee/店家)作適當的轉換。例如把 Cash ->錢包。
* 指令: 
   
    python PM2Moze.py list

* 執行後會產生 PM_all_lists.xlsx ，可以用excel或是google document編輯。編輯完另存成 PM_all_lists.translated.xlsx
* 如果沒有要轉換的話，當然也可以不去動他，或是直接跳過這一步驟。

**步驟3：開始轉換資料**
* 執行以下指令

    python PM2Moze.py convert

* 確認各階段都正常運行，最後預設轉換好的資料會放在 MOZE.csv
* 在匯入前，先打開MOZE.csv看一下格式有沒有錯得很誇張，有的話請回報或自己動手修好 ^^ (格式可參照[官方文件](https://docs.google.com/spreadsheets/d/11otNPygy8Ba2LSV8hJyzwa2XW7q4OdWjsQ5Uvjbk9rw/edit#gid=0))
* 在匯入前，還要記得把原來MOZE裡的資料備份(用icloud或是DropBox都可以)
* follow [MOZE 3.0 官方匯入方式](https://moze.app/features/import-export--import) (請參照 [官方網站](https://moze.app))
* 等一下下 (我的24542筆資料花了30~60秒)
* 如果 MOZE 反應格式有問題，一樣請回報或自己動手修好 :D
* 最後進App 確認一下金額是否正確，小差異的話應該是外幣轉換匯率的問題，請用「餘額調整」的功能補正即可。套句作者的話：
    >過去讓它過去，不用糾結這些數字差異，重點只是把舊資料內容放在 MOZE 內，直接用餘額調整把所有帳戶跟現實餘額一致，然後開始新的記帳生活吧
  
    

Future:
----
* English version (?) if someone really need English version, please let me know


References and Personal thought:
----
* Code structure and concept: [AndroMoney to MOZE transformater](https://github.com/Lee-W/AndroMoney_to_MOZE_transformater) 感謝[Wei Lee](https://github.com/Lee-W)寫了這個程式，並且在他的blog裡分享了心得。我一開始是先看到他的[這篇文章](https://lee-w.github.io/posts/tech/2018/09/from-andromoney-to-moze/)之後，才真正下定決心要自己學python，然後寫一個 PM to MOZE 的工具出來。在思考程式架構的過程中也有大量參考他的作品。不過因為PM2的資料太髒，所以要處理的東西更多，花了不少時間在這個上面。
* [Pandas](https://pandas.pydata.org/docs/)：很好用的資料處理工具，如果不要逐筆處理資料，速度真的很快。可惜針對PM轉帳的部份要逐筆比對，這時就慢了一點。但是再怎麼慢，應該都不會跑超過1分鐘...
* Moze 3.0 [官方網站](https://moze.app)
  

