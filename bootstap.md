Requirements
I want to create a data processing script that is used to take a set of Templates and adds the metadata to each column to create a set of Import Templates to support a Data Migration. The processing script should ask the user to select a local folder that contains the Templates - then loops through all the csv and excel files in the folder and adds metadata for each column header from an XML dictionary. The XML dictionary contains definitions of the metadata associated with each column header of the Templates. The xml file also needs to be read in and used to lookup and extract the metadata if each column. At the end of the script the output will be a set of Target Templates that mimic the Templates but have the metadata added as additional rows.

Steps
1. Ask the User for the (local) folder that contains the set of Templates.
2. Read in all the csv and excel files. Each file should contain two rows: the first row contains the column header (known as the "Property Name" in the XML) while the second row contains a freeform Description of what the fields contains and what valid values the data could be.
3. If the file does not contain two rows then flag it as such.
4. Allow the csv and excel files that have been read in to be deleted interactively by the user.
5. For each "Property Name"  look up the following metadata from the XML file and add a row to the Import Template: Property Name -> Column Name, Type  -> see point 6 below, sap:required -> Mandatory, MaxLength -> Max Length, and the original freeform Description -> Description.
6. The following is the set of example Types:- 
a) string:"Edm.String"
b) float:"Edm.Decimal"
c) date:"Edm.DateTime"
d) integer: Type="Edm.Int64"
e) boolean is Type="Edm.Boolean"
f) picklist is a custom category.
7. The output should be a set of files that can be downloaded. Each file should contain the original header across the top - and 4 additional rows. Row 1 - Column Name, Row 2 - Description, Row 3 - Type, Row 4 - Mandatory, Row 5 - Max Length.
8. Allow the user to download the output files in csv or xlsx.