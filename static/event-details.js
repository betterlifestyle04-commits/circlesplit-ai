"use strict";
/* UI preflight; server applies the authoritative consent and payment guard. */
function validEventDate(day){
 if(typeof day!=="string"||!/^\d{4}-\d{2}-\d{2}$/.test(day))return false;
 const [year,month,dayOfMonth]=day.split("-").map(Number);
 const result=new Date(Date.UTC(year,month-1,dayOfMonth));
 return result.getUTCFullYear()===year&&
        result.getUTCMonth()===month-1&&result.getUTCDate()===dayOfMonth;
}
function prepareEventDetails(name,date,note,original){
 if(!original||typeof original.name!=="string"||
    typeof original.date!=="string"||typeof original.note!=="string")
  throw Error("The event has changed. Reload it before editing.");
 const title=String(name??"").trim(),description=String(note??"").trim();
 if(title.length<3||title.length>90)throw Error("Name must contain 3–90 characters.");
 if(!validEventDate(date))throw Error("Choose a valid calendar date.");
 if(description.length>180)throw Error("Description cannot exceed 180 characters.");
 const body={name:title,date,note:description,expected_name:original.name,
             expected_date:original.date,expected_note:original.note};
 return {body,changed:title!==original.name||date!==original.date||
                      description!==original.note};
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={validEventDate,prepareEventDetails};
